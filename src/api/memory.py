"""
Memory API — channel-facing endpoints for submitting content.
These endpoints are accessible to configured channels.
No endpoint here may directly create a MemoryItem — only MemoryCandidates.
"""

import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.gateway import ChannelGateway, NormalizedMessage, PermissionDeniedError
from src.database import get_db
from src.memory.service import MemoryService
from src.models.channel_config import PermissionLevel

logger = logging.getLogger(__name__)
router = APIRouter()


class InboundMessageRequest(BaseModel):
    channel_id: str
    channel_type: str
    sender_id: str
    sender_name: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=10_000)
    message_id: Optional[str] = None


class InboundMessageResponse(BaseModel):
    status: str
    permission_level: str
    candidate_id: Optional[str] = None
    message: str


@router.post("/ingest", response_model=InboundMessageResponse)
async def ingest_message(
    body: InboundMessageRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InboundMessageResponse:
    """
    Receive a normalized inbound message from any channel.
    The endpoint enforces permission policy via ChannelGateway before any action.
    """
    normalized = NormalizedMessage(
        channel_id=body.channel_id,
        channel_type=body.channel_type,
        sender_id=body.sender_id,
        sender_name=body.sender_name or "",
        content=body.content,
        message_id=body.message_id or "",
    )

    gateway = ChannelGateway(db)
    try:
        decision = await gateway.route_message(normalized)
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc

    permission = decision.permission_level

    if permission == PermissionLevel.read_only_chat:
        # No memory operations — just acknowledge
        return InboundMessageResponse(
            status="accepted",
            permission_level=permission,
            message="Message received. Chat response not yet implemented in MVP.",
        )

    if permission in (PermissionLevel.learn_candidate, PermissionLevel.admin):
        # Create a candidate for review — never write MemoryItem directly.
        # LLM is not needed here; embedding is generated only at approval time.
        service = MemoryService(db=db)
        candidate = await service.create_candidate(
            proposed_content=body.content,
            proposed_type="conversation",
            actor=f"{body.channel_id}:{body.sender_id}",
            metadata={
                "channel_type": body.channel_type,
                "sender_name": body.sender_name,
                "message_id": body.message_id,
            },
        )
        return InboundMessageResponse(
            status="candidate_created",
            permission_level=permission,
            candidate_id=str(candidate.id),
            message="Memory candidate created and queued for admin review.",
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unhandled permission level",
    )
