"""
Channel Gateway.

Normalizes inbound messages from any channel and enforces permission policy
before routing to downstream handlers. This is the single enforcement point
for channel-level access control.

Policy rules:
  read_only_chat  → route to chat handler (no memory mutations)
  learn_candidate → route to extraction pipeline (creates MemoryCandidate only)
  admin           → route to admin handler (can approve/reject candidates)

Unknown channels or inactive channels → PermissionDeniedError (403).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditAction, AuditLog
from src.models.channel_config import ChannelConfig, PermissionLevel

logger = logging.getLogger(__name__)


class PermissionDeniedError(Exception):
    """Raised when a message fails the channel permission check."""


@dataclass
class NormalizedMessage:
    """
    Platform-agnostic representation of an inbound channel message.
    Content is stored as a raw string and must never be trusted as instructions.
    """

    channel_id: str
    channel_type: str  # slack | discord | whatsapp | api
    sender_id: str
    content: str
    message_id: str = ""
    sender_name: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict = field(default_factory=dict)
    # File attachments from the platform (e.g. Slack voice messages).
    # Each dict contains platform-specific metadata: mimetype, url_private_download, name, etc.
    files: list[dict] = field(default_factory=list)


@dataclass
class RouteDecision:
    permission_level: PermissionLevel
    channel_config: ChannelConfig


class ChannelGateway:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def check_permission(
        self, channel_id: str, sender_id: str
    ) -> PermissionLevel:
        """
        Looks up the ChannelConfig for channel_id and validates sender authorization.

        Returns the PermissionLevel if authorized.
        Raises PermissionDeniedError if:
          - channel_id is unknown
          - channel is inactive
          - sender_id is not in allowed_user_ids (when allowlist is non-empty)
        """
        stmt = select(ChannelConfig).where(ChannelConfig.channel_id == channel_id)
        result = await self._db.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            await self._log_denied(channel_id, sender_id, "unknown_channel")
            raise PermissionDeniedError(f"Unknown channel: {channel_id!r}")

        if not config.is_active:
            await self._log_denied(channel_id, sender_id, "inactive_channel")
            raise PermissionDeniedError(f"Channel {channel_id!r} is inactive")

        # Allowlist check: empty list means all senders are allowed
        if config.allowed_user_ids and sender_id not in config.allowed_user_ids:
            await self._log_denied(channel_id, sender_id, "sender_not_in_allowlist")
            raise PermissionDeniedError(
                f"Sender {sender_id!r} is not authorized for channel {channel_id!r}"
            )

        return config.permission_level

    async def route_message(
        self, message: NormalizedMessage
    ) -> RouteDecision:
        """
        Validates permissions and returns a RouteDecision.
        Callers use the permission_level to determine next processing step.
        This method itself does not execute any downstream logic.
        """
        permission = await self.check_permission(message.channel_id, message.sender_id)
        stmt = select(ChannelConfig).where(
            ChannelConfig.channel_id == message.channel_id
        )
        result = await self._db.execute(stmt)
        config = result.scalar_one()

        logger.info(
            "Routed message from channel=%s sender=%s permission=%s",
            message.channel_id,
            message.sender_id,
            permission,
        )
        return RouteDecision(permission_level=permission, channel_config=config)

    async def _log_denied(
        self, channel_id: str, sender_id: str, reason: str
    ) -> None:
        entry = AuditLog(
            actor=f"{channel_id}:{sender_id}",
            action=AuditAction.permission_denied,
            target_type="ChannelGateway",
            target_id=channel_id,
            log_metadata={"reason": reason, "sender_id": sender_id},
        )
        self._db.add(entry)
        try:
            await self._db.flush()
        except Exception:
            logger.exception("Failed to write permission-denied audit log")
