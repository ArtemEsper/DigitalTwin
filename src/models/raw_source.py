import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, new_uuid


class SourceType(str, enum.Enum):
    article = "article"
    document = "document"
    transcript = "transcript"
    conversation = "conversation"
    other = "other"


class RawSource(Base, TimestampMixin):
    """
    Stores raw ingested content with full provenance.
    Content is never interpolated directly into LLM prompts.
    """

    __tablename__ = "dt_raw_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # JSONB metadata: author, date, language, word_count, etc.
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # processing_status: pending | extracted | failed
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
