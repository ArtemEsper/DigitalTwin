"""
Tests for channel permission logic.

Verifies that:
- read_only_chat channels return the correct permission level
- learn_candidate channels return the correct permission level
- admin channels enforce the allowed_user_ids allowlist
- unknown channels raise PermissionDeniedError
- inactive channels raise PermissionDeniedError
- senders not in allowlist raise PermissionDeniedError
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.gateway import ChannelGateway, NormalizedMessage, PermissionDeniedError
from src.models.channel_config import ChannelConfig, ChannelType, PermissionLevel


@pytest.mark.asyncio
async def test_readonly_channel_returns_correct_permission(
    db_session: AsyncSession, readonly_channel: ChannelConfig
):
    gateway = ChannelGateway(db_session)
    level = await gateway.check_permission("slack:C_READONLY", "U_ANY")
    assert level == PermissionLevel.read_only_chat


@pytest.mark.asyncio
async def test_learn_channel_returns_correct_permission(
    db_session: AsyncSession, learn_channel: ChannelConfig
):
    gateway = ChannelGateway(db_session)
    level = await gateway.check_permission("slack:C_LEARN", "U_ANY")
    assert level == PermissionLevel.learn_candidate


@pytest.mark.asyncio
async def test_admin_channel_allows_listed_sender(
    db_session: AsyncSession, admin_channel: ChannelConfig
):
    gateway = ChannelGateway(db_session)
    level = await gateway.check_permission("slack:C_ADMIN", "U_ADMIN_1")
    assert level == PermissionLevel.admin


@pytest.mark.asyncio
async def test_admin_channel_rejects_unlisted_sender(
    db_session: AsyncSession, admin_channel: ChannelConfig
):
    gateway = ChannelGateway(db_session)
    with pytest.raises(PermissionDeniedError):
        await gateway.check_permission("slack:C_ADMIN", "U_INTRUDER")


@pytest.mark.asyncio
async def test_unknown_channel_raises_permission_denied(db_session: AsyncSession):
    gateway = ChannelGateway(db_session)
    with pytest.raises(PermissionDeniedError):
        await gateway.check_permission("slack:C_UNKNOWN", "U_ANY")


@pytest.mark.asyncio
async def test_inactive_channel_raises_permission_denied(db_session: AsyncSession):
    config = ChannelConfig(
        channel_id="slack:C_INACTIVE",
        channel_type=ChannelType.slack,
        permission_level=PermissionLevel.read_only_chat,
        is_active=False,
    )
    db_session.add(config)
    await db_session.flush()

    gateway = ChannelGateway(db_session)
    with pytest.raises(PermissionDeniedError):
        await gateway.check_permission("slack:C_INACTIVE", "U_ANY")


@pytest.mark.asyncio
async def test_route_message_returns_decision(
    db_session: AsyncSession, learn_channel: ChannelConfig
):
    gateway = ChannelGateway(db_session)
    msg = NormalizedMessage(
        channel_id="slack:C_LEARN",
        channel_type="slack",
        sender_id="U_ANY",
        content="test message",
    )
    decision = await gateway.route_message(msg)
    assert decision.permission_level == PermissionLevel.learn_candidate


@pytest.mark.asyncio
async def test_permission_denied_writes_audit_log(
    db_session: AsyncSession,
):
    """A denied message should create an AuditLog entry with action=permission_denied."""
    from sqlalchemy import select
    from src.models.audit_log import AuditAction, AuditLog

    gateway = ChannelGateway(db_session)
    with pytest.raises(PermissionDeniedError):
        await gateway.check_permission("slack:C_GHOST", "U_ANY")

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == AuditAction.permission_denied)
    )
    logs = result.scalars().all()
    assert len(logs) >= 1
    assert logs[-1].target_id == "slack:C_GHOST"
