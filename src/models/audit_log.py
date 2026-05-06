import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, new_uuid


class AuditAction(str, enum.Enum):
    read = "read"
    write = "write"
    delete = "delete"
    approve = "approve"
    reject = "reject"
    export = "export"
    permission_denied = "permission_denied"


class AuditLog(Base):
    """
    Append-only audit trail for all memory operations.

    IMPORTANT: No UPDATE or DELETE methods must ever be exposed for this model.
    The table should be protected at the DB level with a trigger in production.
    """

    __tablename__ = "dt_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=new_uuid
    )
    # Who performed the action (channel_id, user_id, or "system")
    actor: Mapped[str] = mapped_column(String(512), nullable=False)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action_enum"), nullable=False
    )
    target_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Arbitrary context: request path, IP, model used, etc.
    log_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Server-side timestamp — not overridable by client
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
