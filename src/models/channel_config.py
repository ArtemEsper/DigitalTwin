import enum
import uuid

from sqlalchemy import ARRAY, Boolean, Enum, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, new_uuid


class ChannelType(str, enum.Enum):
    slack = "slack"
    discord = "discord"
    whatsapp = "whatsapp"
    api = "api"


class PermissionLevel(str, enum.Enum):
    read_only_chat = "read_only_chat"
    learn_candidate = "learn_candidate"
    admin = "admin"


class ChannelConfig(Base, TimestampMixin):
    """
    Per-channel permission configuration.
    All inbound messages are checked against this table before processing.
    Unknown channels receive 403 Forbidden.
    """

    __tablename__ = "dt_channel_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    # Platform-specific channel identifier (e.g., Slack workspace+channel ID)
    channel_id: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )
    channel_type: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channel_type_enum"), nullable=False
    )
    permission_level: Mapped[PermissionLevel] = mapped_column(
        Enum(PermissionLevel, name="permission_level_enum"),
        nullable=False,
        default=PermissionLevel.read_only_chat,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Empty list means all senders in the channel are authorized at permission_level.
    # Non-empty list restricts to specific sender IDs.
    allowed_user_ids: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(512)), nullable=True
    )
    channel_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
