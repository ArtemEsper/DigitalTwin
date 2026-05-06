"""
Digital Twin Memory Service.

This module is the ONLY authorized path for reading and writing Digital Twin memory.
It must never import development memory tooling (MemPalace or similar).
All write operations produce audit log entries before returning.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.llm.base import BaseLLMProvider
from src.models.audit_log import AuditAction, AuditLog
from src.models.memory_candidate import CandidateStatus, MemoryCandidate
from src.models.memory_item import MemoryItem, MemoryStatus, MemoryType

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Manages Digital Twin memory lifecycle:
    - create_candidate: proposes a new memory for review
    - approve_candidate: promotes a candidate to long-term memory
    - reject_candidate: marks a candidate as rejected
    - retrieve_relevant: semantic similarity search over active memories
    """

    def __init__(self, db: AsyncSession, llm: Optional[BaseLLMProvider] = None) -> None:
        self._db = db
        self._llm = llm

    # ------------------------------------------------------------------
    # Candidate pipeline
    # ------------------------------------------------------------------

    async def create_candidate(
        self,
        proposed_content: str,
        proposed_type: str,
        actor: str,
        proposed_confidence: float = 0.8,
        proposed_tags: Optional[list[str]] = None,
        raw_source_id: Optional[uuid.UUID] = None,
        metadata: Optional[dict] = None,
    ) -> MemoryCandidate:
        """
        Creates a MemoryCandidate in `pending` state.
        No memory item is created here — admin approval is required.
        """
        candidate = MemoryCandidate(
            raw_source_id=raw_source_id,
            proposed_content=proposed_content,
            proposed_type=proposed_type,
            proposed_confidence=proposed_confidence,
            proposed_tags=proposed_tags,
            status=CandidateStatus.pending,
            candidate_metadata=metadata,
        )
        self._db.add(candidate)
        await self._db.flush()  # get the ID before audit log

        await self._write_audit(
            actor=actor,
            action=AuditAction.write,
            target_type="MemoryCandidate",
            target_id=str(candidate.id),
            metadata={"status": "pending", "proposed_type": proposed_type},
        )
        logger.info("Created MemoryCandidate %s (type=%s)", candidate.id, proposed_type)
        return candidate

    async def approve_candidate(
        self,
        candidate_id: uuid.UUID,
        reviewer_id: str,
    ) -> MemoryItem:
        """
        Promotes an approved candidate to a MemoryItem.
        Generates an embedding and writes an audit entry.
        Raises ValueError if candidate is not in `pending` state.
        """
        candidate = await self._get_candidate(candidate_id)
        if candidate.status != CandidateStatus.pending:
            raise ValueError(
                f"Candidate {candidate_id} is in state {candidate.status!r}, "
                "expected 'pending'"
            )

        # Generate embedding
        embedding: Optional[list[float]] = None
        try:
            if self._llm is None:
                raise NotImplementedError
            embed_response = await self._llm.embed(candidate.proposed_content)
            embedding = embed_response.embedding
        except NotImplementedError:
            logger.warning(
                "Embedding not available for provider; storing without embedding"
            )
        except Exception:
            logger.exception("Embedding generation failed for candidate %s", candidate_id)

        # Create MemoryItem
        memory_item = MemoryItem(
            subject_id=settings.SUBJECT_ID,
            memory_type=MemoryType(candidate.proposed_type),
            content=candidate.proposed_content,
            embedding=embedding,
            source_ids=(
                [str(candidate.raw_source_id)] if candidate.raw_source_id else None
            ),
            confidence=candidate.proposed_confidence,
            tags=candidate.proposed_tags,
            status=MemoryStatus.active,
            item_metadata={"approved_by": reviewer_id},
        )
        self._db.add(memory_item)

        # Update candidate status
        candidate.status = CandidateStatus.approved
        candidate.reviewer_id = reviewer_id
        candidate.reviewed_at = datetime.now(timezone.utc)
        self._db.add(candidate)

        await self._db.flush()

        await self._write_audit(
            actor=reviewer_id,
            action=AuditAction.approve,
            target_type="MemoryCandidate",
            target_id=str(candidate_id),
            metadata={"memory_item_id": str(memory_item.id)},
        )
        await self._write_audit(
            actor=reviewer_id,
            action=AuditAction.write,
            target_type="MemoryItem",
            target_id=str(memory_item.id),
            metadata={"memory_type": memory_item.memory_type},
        )
        logger.info(
            "Approved candidate %s → MemoryItem %s", candidate_id, memory_item.id
        )
        return memory_item

    async def approve_all_pending(self, reviewer_id: str) -> list[MemoryItem]:
        """
        Bulk-approve every MemoryCandidate currently in `pending` state.

        Runs in a single database transaction. Embeddings are attempted for
        each item but failures are non-fatal (items are stored without an
        embedding). One summary audit log entry is written for the entire batch.
        """
        stmt = select(MemoryCandidate).where(
            MemoryCandidate.status == CandidateStatus.pending
        )
        result = await self._db.execute(stmt)
        candidates = list(result.scalars().all())

        if not candidates:
            return []

        now = datetime.now(timezone.utc)
        memory_items: list[MemoryItem] = []

        for candidate in candidates:
            embedding: Optional[list[float]] = None
            try:
                if self._llm is None:
                    raise NotImplementedError
                embed_response = await self._llm.embed(candidate.proposed_content)
                embedding = embed_response.embedding
            except NotImplementedError:
                pass
            except Exception:
                logger.exception(
                    "Embedding failed for candidate %s (bulk approve)", candidate.id
                )

            item = MemoryItem(
                subject_id=settings.SUBJECT_ID,
                memory_type=MemoryType(candidate.proposed_type),
                content=candidate.proposed_content,
                embedding=embedding,
                source_ids=(
                    [str(candidate.raw_source_id)] if candidate.raw_source_id else None
                ),
                confidence=candidate.proposed_confidence,
                tags=candidate.proposed_tags,
                status=MemoryStatus.active,
                item_metadata={"approved_by": reviewer_id, "bulk": True},
            )
            self._db.add(item)
            memory_items.append(item)

            candidate.status = CandidateStatus.approved
            candidate.reviewer_id = reviewer_id
            candidate.reviewed_at = now
            self._db.add(candidate)

        await self._db.flush()

        await self._write_audit(
            actor=reviewer_id,
            action=AuditAction.approve,
            target_type="MemoryCandidate",
            target_id=None,
            metadata={"bulk": True, "count": len(memory_items)},
        )
        logger.info("Bulk-approved %d candidates → %d MemoryItems", len(candidates), len(memory_items))
        return memory_items

    async def reject_candidate(
        self,
        candidate_id: uuid.UUID,
        reviewer_id: str,
        reason: Optional[str] = None,
    ) -> MemoryCandidate:
        """
        Marks a candidate as rejected. No MemoryItem is created.
        Raises ValueError if candidate is not in `pending` state.
        """
        candidate = await self._get_candidate(candidate_id)
        if candidate.status != CandidateStatus.pending:
            raise ValueError(
                f"Candidate {candidate_id} is in state {candidate.status!r}, "
                "expected 'pending'"
            )

        candidate.status = CandidateStatus.rejected
        candidate.reviewer_id = reviewer_id
        candidate.reviewed_at = datetime.now(timezone.utc)
        candidate.rejection_reason = reason
        self._db.add(candidate)
        await self._db.flush()

        await self._write_audit(
            actor=reviewer_id,
            action=AuditAction.reject,
            target_type="MemoryCandidate",
            target_id=str(candidate_id),
            metadata={"reason": reason},
        )
        logger.info("Rejected candidate %s (reason=%s)", candidate_id, reason)
        return candidate

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def retrieve_relevant(
        self,
        query: str,
        limit: int = 10,
        min_confidence: float = 0.6,
        actor: str = "system",
    ) -> list[MemoryItem]:
        """
        Retrieves MemoryItems semantically similar to `query` using pgvector cosine distance.
        Falls back to recency-ordered retrieval if embedding is unavailable.
        Always writes an audit log entry.
        """
        embedding: Optional[list[float]] = None
        try:
            if self._llm is None:
                raise NotImplementedError
            embed_response = await self._llm.embed(query)
            embedding = embed_response.embedding
        except (NotImplementedError, Exception):
            logger.warning("Embedding unavailable; falling back to recency retrieval")

        if embedding is not None:
            stmt = (
                select(MemoryItem)
                .where(
                    MemoryItem.status == MemoryStatus.active,
                    MemoryItem.subject_id == settings.SUBJECT_ID,
                    MemoryItem.confidence >= min_confidence,
                )
                .order_by(MemoryItem.embedding.cosine_distance(embedding))
                .limit(limit)
            )
        else:
            stmt = (
                select(MemoryItem)
                .where(
                    MemoryItem.status == MemoryStatus.active,
                    MemoryItem.subject_id == settings.SUBJECT_ID,
                    MemoryItem.confidence >= min_confidence,
                )
                .order_by(MemoryItem.created_at.desc())
                .limit(limit)
            )

        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        await self._write_audit(
            actor=actor,
            action=AuditAction.read,
            target_type="MemoryItem",
            target_id=None,
            metadata={"query_length": len(query), "results": len(items)},
        )
        return items

    async def soft_delete(
        self, memory_item_id: uuid.UUID, actor: str
    ) -> MemoryItem:
        """
        Soft-deletes a MemoryItem: sets status=deleted and zeroes the embedding.
        """
        stmt = select(MemoryItem).where(MemoryItem.id == memory_item_id)
        result = await self._db.execute(stmt)
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"MemoryItem {memory_item_id} not found")

        item.status = MemoryStatus.deleted
        item.embedding = [0.0] * settings.EMBEDDING_DIM
        self._db.add(item)
        await self._db.flush()

        await self._write_audit(
            actor=actor,
            action=AuditAction.delete,
            target_type="MemoryItem",
            target_id=str(memory_item_id),
        )
        return item

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_candidate(self, candidate_id: uuid.UUID) -> MemoryCandidate:
        stmt = select(MemoryCandidate).where(MemoryCandidate.id == candidate_id)
        result = await self._db.execute(stmt)
        candidate = result.scalar_one_or_none()
        if candidate is None:
            raise ValueError(f"MemoryCandidate {candidate_id} not found")
        return candidate

    async def _write_audit(
        self,
        actor: str,
        action: AuditAction,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        entry = AuditLog(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            log_metadata=metadata,
        )
        self._db.add(entry)
        await self._db.flush()
