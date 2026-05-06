import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, new_uuid


class ChatSession(Base, TimestampMixin):
    """
    Records a single question/response exchange with the Digital Twin.

    Stored so that:
    - The subject can read a response and submit a correction referencing it.
    - WhatsApp and other channels can maintain conversation context.
    - The audit trail shows which memories informed each answer.
    """

    __tablename__ = "dt_chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    # Channel that initiated the session (e.g. "api:local", "whatsapp:+380...")
    channel_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="api:local", index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    memories_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # UUIDs of the MemoryItems that were retrieved for this response
    memory_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Whether the subject has submitted a correction for this session
    has_correction: Mapped[bool] = mapped_column(
        nullable=False, default=False
    )
