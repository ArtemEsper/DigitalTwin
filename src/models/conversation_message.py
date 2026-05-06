import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, new_uuid


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class ConversationMessage(Base, TimestampMixin):
    """
    Records inbound channel messages and outbound agent responses.
    Stored for audit and potential future candidate extraction.
    Content is raw and untrusted — never directly used in prompts.
    """

    __tablename__ = "dt_conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    channel_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    channel_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # External message ID from the channel platform
    channel_message_id: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    sender_id: Mapped[str] = mapped_column(String(256), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Raw content — treated as untrusted input
    content: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name="message_direction_enum"), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Raw platform payload for audit purposes
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
