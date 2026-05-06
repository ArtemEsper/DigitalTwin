"""
Admin API — requires X-Admin-Key header for all endpoints.
Provides candidate review, memory management, and export.
"""

import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_admin_key
from src.database import get_db
from src.ingest.extractor import CandidateExtractor
from src.ingest.parser import parse_file
from src.llm import get_llm_provider
from src.llm.base import BaseLLMProvider, LLMMessage
from src.memory.service import MemoryService
from src.models.chat_session import ChatSession
from src.models.memory_candidate import CandidateStatus, MemoryCandidate
from src.models.memory_item import MemoryItem, MemoryStatus, MemoryType
from src.models.raw_source import RawSource, SourceType

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_llm_or_none() -> BaseLLMProvider | None:
    """Return the configured LLM provider, or None if no API key is set.
    Operations that don't strictly need LLM (candidate approval without
    embedding, soft-delete) will proceed without it."""
    try:
        return get_llm_provider()
    except (ValueError, ImportError):
        return None

AdminKey = Annotated[str, Depends(require_admin_key)]
DB = Annotated[AsyncSession, Depends(get_db)]


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class CandidateSummary(BaseModel):
    id: str
    proposed_content: str
    proposed_type: str
    proposed_confidence: float
    status: str
    created_at: str

    class Config:
        from_attributes = True


class ApproveRequest(BaseModel):
    reviewer_id: str = "admin"


class RejectRequest(BaseModel):
    reviewer_id: str = "admin"
    reason: Optional[str] = None


class MemoryItemSummary(BaseModel):
    id: str
    subject_id: str
    memory_type: str
    content: str
    confidence: float
    status: str
    tags: Optional[list[str]]
    created_at: str

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# Candidate review
# ------------------------------------------------------------------


@router.get("/candidates", response_model=list[CandidateSummary])
async def list_candidates(
    _: AdminKey,
    db: DB,
    status_filter: str = "pending",
) -> list[CandidateSummary]:
    """List memory candidates filtered by status."""
    stmt = select(MemoryCandidate).where(
        MemoryCandidate.status == CandidateStatus(status_filter)
    ).order_by(MemoryCandidate.created_at.asc())
    result = await db.execute(stmt)
    candidates = result.scalars().all()
    return [
        CandidateSummary(
            id=str(c.id),
            proposed_content=c.proposed_content,
            proposed_type=c.proposed_type,
            proposed_confidence=c.proposed_confidence,
            status=c.status,
            created_at=c.created_at.isoformat(),
        )
        for c in candidates
    ]


@router.post("/candidates/approve-all-pending")
async def approve_all_pending_candidates(
    body: ApproveRequest,
    _: AdminKey,
    db: DB,
) -> dict:
    """Bulk-approve every pending candidate in a single transaction."""
    service = MemoryService(db=db, llm=_get_llm_or_none())
    items = await service.approve_all_pending(reviewer_id=body.reviewer_id)
    return {"status": "approved", "memory_items_created": len(items)}


@router.post("/candidates/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: uuid.UUID,
    body: ApproveRequest,
    _: AdminKey,
    db: DB,
) -> dict:
    service = MemoryService(db=db, llm=_get_llm_or_none())
    try:
        item = await service.approve_candidate(
            candidate_id=candidate_id, reviewer_id=body.reviewer_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"status": "approved", "memory_item_id": str(item.id)}


@router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: uuid.UUID,
    body: RejectRequest,
    _: AdminKey,
    db: DB,
) -> dict:
    service = MemoryService(db=db, llm=_get_llm_or_none())
    try:
        await service.reject_candidate(
            candidate_id=candidate_id,
            reviewer_id=body.reviewer_id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"status": "rejected"}


# ------------------------------------------------------------------
# Memory management
# ------------------------------------------------------------------


@router.get("/memory", response_model=list[MemoryItemSummary])
async def list_memory_items(
    _: AdminKey,
    db: DB,
) -> list[MemoryItemSummary]:
    """List all active memory items."""
    stmt = (
        select(MemoryItem)
        .where(MemoryItem.status == MemoryStatus.active)
        .order_by(MemoryItem.created_at.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        MemoryItemSummary(
            id=str(i.id),
            subject_id=i.subject_id,
            memory_type=i.memory_type,
            content=i.content,
            confidence=i.confidence,
            status=i.status,
            tags=i.tags,
            created_at=i.created_at.isoformat(),
        )
        for i in items
    ]


@router.delete("/memory/{memory_item_id}")
async def delete_memory_item(
    memory_item_id: uuid.UUID,
    _: AdminKey,
    db: DB,
) -> dict:
    """Soft-delete a memory item (sets status=deleted, zeroes embedding)."""
    service = MemoryService(db=db, llm=_get_llm_or_none())
    try:
        await service.soft_delete(memory_item_id=memory_item_id, actor="admin")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"status": "deleted"}


# ------------------------------------------------------------------
# Document ingest
# ------------------------------------------------------------------


class IngestSourceRequest(BaseModel):
    content: str
    source_type: str = "document"  # article | document | transcript | conversation
    extraction_mode: str = "biographical"  # biographical | authored_work
    title: Optional[str] = None
    url: Optional[str] = None
    subject_hint: Optional[str] = None  # e.g. "Alice Smith, software engineer"


class IngestSourceResponse(BaseModel):
    source_id: str
    candidates_created: int
    candidate_ids: list[str]


@router.post("/sources", response_model=IngestSourceResponse)
async def ingest_source(
    body: IngestSourceRequest,
    _: AdminKey,
    db: DB,
) -> IngestSourceResponse:
    """
    Ingest a document and extract memory candidates via LLM.
    The document is stored as a RawSource. The LLM extracts structured
    memories which are stored as MemoryCandidate records (pending review).
    No MemoryItem is created — candidates still require admin approval.
    """
    llm = get_llm_provider()

    # Store the raw source
    raw_source = RawSource(
        source_type=SourceType(body.source_type),
        title=body.title,
        content=body.content,
        url=body.url,
        processing_status="pending",
    )
    db.add(raw_source)
    await db.flush()

    # Extract memory candidates using the LLM
    extractor = CandidateExtractor(llm=llm)
    from src.config import settings
    subject_hint = body.subject_hint or settings.SUBJECT_ID
    results = await extractor.extract(body.content, subject_hint=subject_hint, extraction_mode=body.extraction_mode)

    # Store each extraction result as a pending MemoryCandidate
    memory_service = MemoryService(db=db, llm=None)
    candidate_ids = []
    for result in results:
        candidate = await memory_service.create_candidate(
            proposed_content=result.content,
            proposed_type=result.memory_type,
            actor="admin:ingest",
            proposed_confidence=result.confidence,
            proposed_tags=result.tags,
            raw_source_id=raw_source.id,
            metadata={"source_title": body.title, "extracted_by": "CandidateExtractor"},
        )
        candidate_ids.append(str(candidate.id))

    # Mark source as extracted
    raw_source.processing_status = "extracted"
    db.add(raw_source)

    return IngestSourceResponse(
        source_id=str(raw_source.id),
        candidates_created=len(candidate_ids),
        candidate_ids=candidate_ids,
    )


@router.post("/sources/upload", response_model=IngestSourceResponse)
async def upload_source(
    _: AdminKey,
    db: DB,
    file: UploadFile = File(...),
    source_type: str = Form("document"),
    extraction_mode: str = Form("biographical"),
    subject_hint: str = Form(""),
    title: str = Form(""),
) -> IngestSourceResponse:
    """
    Upload a .pdf, .docx, or .txt file, extract its text, and run the
    candidate extraction pipeline. Identical to POST /sources but accepts
    a file instead of raw text.
    """
    data = await file.read()
    filename = file.filename or "upload"

    try:
        text = parse_file(filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    llm = get_llm_provider()

    raw_source = RawSource(
        source_type=SourceType(source_type),
        title=title or filename,
        content=text,
        file_path=filename,
        processing_status="pending",
    )
    db.add(raw_source)
    await db.flush()

    extractor = CandidateExtractor(llm=llm)
    from src.config import settings
    results = await extractor.extract(text, subject_hint=subject_hint or settings.SUBJECT_ID, extraction_mode=extraction_mode)

    memory_service = MemoryService(db=db, llm=None)
    candidate_ids = []
    for result in results:
        candidate = await memory_service.create_candidate(
            proposed_content=result.content,
            proposed_type=result.memory_type,
            actor="admin:upload",
            proposed_confidence=result.confidence,
            proposed_tags=result.tags,
            raw_source_id=raw_source.id,
            metadata={"filename": filename, "extracted_by": "CandidateExtractor"},
        )
        candidate_ids.append(str(candidate.id))

    raw_source.processing_status = "extracted"
    db.add(raw_source)

    return IngestSourceResponse(
        source_id=str(raw_source.id),
        candidates_created=len(candidate_ids),
        candidate_ids=candidate_ids,
    )


class ChatRequest(BaseModel):
    message: str
    memory_limit: int = 30
    channel_id: str = "api:local"


class ChatResponse(BaseModel):
    session_id: str
    response: str
    memories_used: int


class CorrectionRequest(BaseModel):
    correction: str          # What the subject says is actually true
    reviewer_id: str = "subject"


class CorrectionResponse(BaseModel):
    memory_item_id: str
    status: str = "approved"


@router.post("/chat")
async def chat(
    body: ChatRequest,
    _: AdminKey,
    db: DB,
) -> ChatResponse:
    """
    Ask a question and receive an answer grounded in stored memories.
    Returns a session_id that can be used to submit a correction.
    """
    from src.config import settings

    llm = get_llm_provider()
    memory_service = MemoryService(db=db, llm=llm)

    memories = await memory_service.retrieve_relevant(
        query=body.message,
        limit=body.memory_limit,
        actor="admin:chat",
    )

    subject_name = settings.SUBJECT_NAME or settings.SUBJECT_ID
    memory_context = _build_memory_context(memories)

    system_prompt = f"""\
You are {subject_name}. The memories below are your own knowledge — your beliefs,
concepts, voice, values, biographical facts, and ideas. They were extracted from
documents you wrote or that were written about you.

Use these memories to answer as yourself:
- Speak in first person ("I believe...", "In my view...", "For me...").
- Match the language of the question — if asked in Ukrainian, answer in Ukrainian.
- Use your characteristic voice and style (see [VOICE] memories).
- Draw on your specific beliefs and concepts rather than giving generic answers.
- If you genuinely don't know something, say so honestly rather than inventing.
- Keep answers focused and in your own style — not academic or impersonal.

{memory_context}"""

    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=body.message),
    ]

    llm_response = await llm.complete(messages, max_tokens=1024, temperature=0.7)

    # Persist the session so the subject can correct it later
    session = ChatSession(
        channel_id=body.channel_id,
        question=body.message,
        response=llm_response.content,
        memories_used=len(memories),
        memory_ids=[str(m.id) for m in memories],
    )
    db.add(session)
    await db.flush()

    return ChatResponse(
        session_id=str(session.id),
        response=llm_response.content,
        memories_used=len(memories),
    )


@router.post("/chat/{session_id}/correct", response_model=CorrectionResponse)
async def correct_chat_response(
    session_id: uuid.UUID,
    body: CorrectionRequest,
    _: AdminKey,
    db: DB,
) -> CorrectionResponse:
    """
    Submit a correction to a previous chat response.

    The subject reads what the Digital Twin said and provides the true answer.
    The correction is saved as a high-confidence memory and auto-approved —
    the subject is the ground truth for their own knowledge.
    """
    # Load the session so the correction can be contextualised
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Infer the best memory type from the correction text (fallback: idea)
    memory_service = MemoryService(db=db, llm=_get_llm_or_none())

    candidate = await memory_service.create_candidate(
        proposed_content=body.correction,
        proposed_type="idea",
        actor=f"subject:{body.reviewer_id}",
        proposed_confidence=1.0,
        proposed_tags=["subject_correction"],
        metadata={
            "source": "subject_correction",
            "session_id": str(session_id),
            "original_question": session.question,
            "original_response": session.response,
        },
    )

    # Auto-approve: the subject correcting their own twin is ground truth
    item = await memory_service.approve_candidate(
        candidate_id=candidate.id,
        reviewer_id=body.reviewer_id,
    )

    # Mark the session as corrected
    session.has_correction = True
    db.add(session)

    return CorrectionResponse(memory_item_id=str(item.id))


def _build_memory_context(memories: list[MemoryItem]) -> str:
    """
    Format retrieved memories as a labelled context block.
    Identity-defining types (voice, belief, concept, value) come first
    so the LLM establishes the persona before drawing on facts.
    """
    priority = [
        "voice", "belief", "concept", "value",
        "personality", "idea", "biographical",
        "event", "skill", "preference", "relationship", "conversation",
    ]
    order = {t: i for i, t in enumerate(priority)}
    sorted_memories = sorted(memories, key=lambda m: order.get(str(m.memory_type), 99))

    lines = ["--- YOUR MEMORIES ---"]
    for m in sorted_memories:
        lines.append(f"[{str(m.memory_type).upper()}] {m.content}")
    lines.append("--- END MEMORIES ---")
    return "\n".join(lines)


@router.get("/export")
async def export_memory(
    _: AdminKey,
    db: DB,
) -> list[dict]:
    """
    GDPR export: returns all memory items for the subject as JSON.
    Writes an audit log entry with action=export.
    """
    from src.config import settings
    from src.models.audit_log import AuditAction, AuditLog

    stmt = select(MemoryItem).where(MemoryItem.subject_id == settings.SUBJECT_ID)
    result = await db.execute(stmt)
    items = result.scalars().all()

    audit = AuditLog(
        actor="admin",
        action=AuditAction.export,
        target_type="MemoryItem",
        target_id=settings.SUBJECT_ID,
        log_metadata={"count": len(items)},
    )
    db.add(audit)

    return [
        {
            "id": str(i.id),
            "subject_id": i.subject_id,
            "memory_type": i.memory_type,
            "content": i.content,
            "confidence": i.confidence,
            "tags": i.tags,
            "status": i.status,
            "source_ids": i.source_ids,
            "created_at": i.created_at.isoformat(),
            "updated_at": i.updated_at.isoformat(),
        }
        for i in items
    ]
