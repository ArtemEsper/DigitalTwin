import enum
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Enum, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.config import settings
from src.models.base import Base, TimestampMixin, new_uuid


class MemoryType(str, enum.Enum):
    biographical = "biographical"
    personality = "personality"
    idea = "idea"
    event = "event"
    preference = "preference"
    skill = "skill"
    relationship = "relationship"
    conversation = "conversation"
    # Authored-work types — extracted from the subject's own writing
    belief = "belief"       # Deep philosophical/spiritual conviction
    concept = "concept"     # Personal term or framework used in a distinctive way
    voice = "voice"         # Characteristic rhetorical pattern or stylistic marker
    value = "value"         # Core principle revealed as important through the writing


class MemoryStatus(str, enum.Enum):
    active = "active"
    deleted = "deleted"
    exported = "exported"


class MemoryItem(Base, TimestampMixin):
    """
    Approved long-term Digital Twin memory item.
    Only reachable after explicit admin approval of a MemoryCandidate.
    Embeddings enable semantic similarity retrieval via pgvector.
    """

    __tablename__ = "dt_memory_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    subject_id: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="memory_type_enum"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Semantic embedding — dimension set from config at table creation time
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIM), nullable=True
    )
    # UUIDs of originating RawSource records
    source_ids: Mapped[list[str] | None] = mapped_column(
        ARRAY(UUID(as_uuid=False)), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(128)), nullable=True)
    status: Mapped[MemoryStatus] = mapped_column(
        Enum(MemoryStatus, name="memory_status_enum"),
        nullable=False,
        default=MemoryStatus.active,
    )
    # JSONB extra metadata (e.g., extracted_by, model_version)
    item_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
