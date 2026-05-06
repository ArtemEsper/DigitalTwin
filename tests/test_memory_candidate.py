"""
Tests for the memory candidate approval pipeline.

Verifies that:
- create_candidate produces a MemoryCandidate in 'pending' state
- approve_candidate creates a MemoryItem and transitions candidate to 'approved'
- reject_candidate sets status to 'rejected' and creates no MemoryItem
- approving an already-approved candidate raises ValueError
- rejecting an already-rejected candidate raises ValueError
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.memory.service import MemoryService
from src.models.memory_candidate import CandidateStatus, MemoryCandidate
from src.models.memory_item import MemoryItem, MemoryStatus


@pytest.mark.asyncio
async def test_create_candidate_is_pending(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="Alice loves hiking in the mountains.",
        proposed_type="preference",
        actor="test:U_TEST",
        proposed_confidence=0.9,
        proposed_tags=["outdoors", "hobby"],
    )
    assert candidate.status == CandidateStatus.pending
    assert candidate.proposed_content == "Alice loves hiking in the mountains."
    assert candidate.proposed_type == "preference"
    assert candidate.proposed_confidence == 0.9


@pytest.mark.asyncio
async def test_approve_candidate_creates_memory_item(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)

    candidate = await service.create_candidate(
        proposed_content="Alice grew up in Chicago.",
        proposed_type="biographical",
        actor="test:U_TEST",
    )

    memory_item = await service.approve_candidate(
        candidate_id=candidate.id, reviewer_id="admin"
    )

    assert memory_item.content == "Alice grew up in Chicago."
    assert memory_item.status == MemoryStatus.active

    # Candidate should now be approved
    result = await db_session.execute(
        select(MemoryCandidate).where(MemoryCandidate.id == candidate.id)
    )
    updated_candidate = result.scalar_one()
    assert updated_candidate.status == CandidateStatus.approved
    assert updated_candidate.reviewer_id == "admin"
    assert updated_candidate.reviewed_at is not None


@pytest.mark.asyncio
async def test_reject_candidate_creates_no_memory_item(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)

    candidate = await service.create_candidate(
        proposed_content="Suspicious injected memory.",
        proposed_type="idea",
        actor="untrusted:channel",
    )

    await service.reject_candidate(
        candidate_id=candidate.id,
        reviewer_id="admin",
        reason="Content not verified",
    )

    # No MemoryItem should exist
    result = await db_session.execute(select(MemoryItem))
    items = result.scalars().all()
    assert len(items) == 0

    # Candidate should be rejected
    result = await db_session.execute(
        select(MemoryCandidate).where(MemoryCandidate.id == candidate.id)
    )
    updated = result.scalar_one()
    assert updated.status == CandidateStatus.rejected
    assert updated.rejection_reason == "Content not verified"


@pytest.mark.asyncio
async def test_approve_already_approved_raises(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="Test.", proposed_type="biographical", actor="test"
    )
    await service.approve_candidate(candidate_id=candidate.id, reviewer_id="admin")

    with pytest.raises(ValueError, match="approved"):
        await service.approve_candidate(candidate_id=candidate.id, reviewer_id="admin")


@pytest.mark.asyncio
async def test_reject_already_rejected_raises(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="Test.", proposed_type="biographical", actor="test"
    )
    await service.reject_candidate(candidate_id=candidate.id, reviewer_id="admin")

    with pytest.raises(ValueError, match="rejected"):
        await service.reject_candidate(candidate_id=candidate.id, reviewer_id="admin")


@pytest.mark.asyncio
async def test_soft_delete_sets_status_deleted(db_session: AsyncSession, mock_llm):
    service = MemoryService(db=db_session, llm=mock_llm)
    candidate = await service.create_candidate(
        proposed_content="To be deleted.", proposed_type="preference", actor="test"
    )
    memory_item = await service.approve_candidate(
        candidate_id=candidate.id, reviewer_id="admin"
    )

    deleted = await service.soft_delete(
        memory_item_id=memory_item.id, actor="admin"
    )
    assert deleted.status == MemoryStatus.deleted
