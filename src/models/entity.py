import enum
import uuid

from sqlalchemy import ARRAY, Enum, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, new_uuid


class EntityType(str, enum.Enum):
    person = "person"
    place = "place"
    organization = "organization"
    concept = "concept"
    other = "other"


class Entity(Base, TimestampMixin):
    """Named entity extracted from memory sources."""

    __tablename__ = "dt_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="entity_type_enum"), nullable=False
    )
    aliases: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(512)), nullable=True
    )
    entity_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
