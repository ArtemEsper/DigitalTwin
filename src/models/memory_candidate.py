import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, new_uuid


class CandidateStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class MemoryCandidate(Base, TimestampMixin):
    """
    A proposed memory item awaiting admin review.
    No candidate is ever promoted to MemoryItem without explicit approval.
    This is the mandatory gateway between raw content and long-term memory.
    """

    __tablename__ = "dt_memory_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    raw_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dt_raw_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    proposed_content: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_type: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.8
    )
    proposed_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(128)), nullable=True
    )
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, name="candidate_status_enum"),
        nullable=False,
        default=CandidateStatus.pending,
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSONB extras: extraction model, prompt version, channel context
    candidate_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
