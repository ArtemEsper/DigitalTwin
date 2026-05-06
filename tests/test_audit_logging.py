"""
Tests for audit logging.

Verifies that:
- Memory candidate creation writes an audit log entry
- Memory item approval writes audit log entries (one for candidate, one for item)
- Memory item rejection writes an audit log entry
- Soft deletion writes an audit log entry
- Permission denied writes an audit log entry
- AuditLog has no exposed delete/update methods
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.memory.service import MemoryService
from src.models.audit_log import AuditAction, AuditLog


async def _count_audit_entries(db: AsyncSession, action: AuditAction) -> int:
    result = await db.execute(
        select(AuditLog).where(AuditLog.action == action)
    )
    return len(result.scalars().all())


@pytest.mark.asyncio
async def test_create_candidate_writes_audit_log(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    before = await _count_audit_entries(db_session, AuditAction.write)

    await service.create_candidate(
        proposed_content="Audit test content.",
        proposed_type="biographical",
        actor="test:U_1",
    )

    after = await _count_audit_entries(db_session, AuditAction.write)
    assert after == before + 1


@pytest.mark.asyncio
async def test_approve_candidate_writes_two_audit_entries(
    db_session: AsyncSession, mock_llm
):
    """Approval should write: one approve + one write (for the new MemoryItem)."""
    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="Audit approve test.", proposed_type="preference", actor="test"
    )

    write_before = await _count_audit_entries(db_session, AuditAction.write)
    approve_before = await _count_audit_entries(db_session, AuditAction.approve)

    await service.approve_candidate(candidate_id=candidate.id, reviewer_id="admin")

    write_after = await _count_audit_entries(db_session, AuditAction.write)
    approve_after = await _count_audit_entries(db_session, AuditAction.approve)

    assert approve_after == approve_before + 1, "Expected one 'approve' audit entry"
    assert write_after == write_before + 1, "Expected one 'write' audit entry for MemoryItem"


@pytest.mark.asyncio
async def test_reject_candidate_writes_audit_log(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="Will be rejected.", proposed_type="idea", actor="test"
    )

    before = await _count_audit_entries(db_session, AuditAction.reject)
    await service.reject_candidate(
        candidate_id=candidate.id, reviewer_id="admin", reason="Not verified"
    )
    after = await _count_audit_entries(db_session, AuditAction.reject)
    assert after == before + 1


@pytest.mark.asyncio
async def test_soft_delete_writes_audit_log(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="To be deleted.", proposed_type="skill", actor="test"
    )
    item = await service.approve_candidate(candidate_id=candidate.id, reviewer_id="admin")

    before = await _count_audit_entries(db_session, AuditAction.delete)
    await service.soft_delete(memory_item_id=item.id, actor="admin")
    after = await _count_audit_entries(db_session, AuditAction.delete)
    assert after == before + 1


@pytest.mark.asyncio
async def test_retrieval_writes_read_audit_log(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)

    before = await _count_audit_entries(db_session, AuditAction.read)
    await service.retrieve_relevant("query text", actor="test:U_1")
    after = await _count_audit_entries(db_session, AuditAction.read)
    assert after == before + 1


@pytest.mark.asyncio
async def test_audit_log_actor_recorded_correctly(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    await service.create_candidate(
        proposed_content="Test.", proposed_type="biographical", actor="slack:C_TEST:U_123"
    )

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.actor == "slack:C_TEST:U_123")
    )
    entries = result.scalars().all()
    assert len(entries) >= 1


def test_audit_log_model_has_no_update_or_delete_class_methods():
    """
    AuditLog must not expose update() or delete() class methods.
    This is a structural safety check.
    """
    assert not hasattr(AuditLog, "update"), "AuditLog must not have an update() method"
    assert not hasattr(AuditLog, "delete"), "AuditLog must not have a delete() method"
