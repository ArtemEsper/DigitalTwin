"""
Slack Events API webhook endpoint.

Receives incoming Slack messages, verifies the request signature, and
dispatches to the appropriate handler based on channel permission level:

  read_only_chat  → generate a chat response, reply in thread
  learn_candidate → treat the message as a subject correction, auto-approve,
                    reply with confirmation

The endpoint acknowledges Slack immediately (< 3 s) and processes
the event in a FastAPI BackgroundTask.
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from src.channels.gateway import ChannelGateway, NormalizedMessage, PermissionDeniedError
from src.channels.slack_adapter import (
    normalize_slack_event,
    send_message,
    verify_slack_signature,
)
from src.config import settings
from src.database import AsyncSessionLocal
from src.llm import get_llm_provider
from src.llm.base import LLMMessage
from src.memory.service import MemoryService
from src.models.channel_config import PermissionLevel
from src.models.chat_session import ChatSession

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/events")
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Entry point for all Slack Events API deliveries.

    Handles:
      - URL verification challenge (required when first enabling events)
      - message events (dispatched to background processing)
    """
    if not settings.SLACK_SIGNING_SECRET or not settings.SLACK_BOT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack integration not configured. Set SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET in .env",
        )

    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(settings.SLACK_SIGNING_SECRET, body, timestamp, signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Slack signature")

    import json as _json
    payload: dict[str, Any] = _json.loads(body)

    # Slack sends this once when you first configure the Events API URL
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    if payload.get("type") == "event_callback":
        event = payload.get("event", {})

        # Ignore bot messages and non-message events to prevent feedback loops
        if (
            event.get("type") != "message"
            or event.get("bot_id")
            or event.get("subtype") in ("bot_message", "message_changed", "message_deleted")
        ):
            return {"ok": True}

        # Acknowledge immediately — Slack retries if we take > 3 s
        background_tasks.add_task(_handle_message, payload)

    return {"ok": True}


async def _handle_message(payload: dict[str, Any]) -> None:
    """
    Background task: process a single Slack message event.

    Creates its own DB session (the request session is closed by the time
    background tasks run).
    """
    try:
        msg = normalize_slack_event(payload)
    except ValueError as exc:
        logger.warning("Could not normalize Slack event: %s", exc)
        return

    slack_channel = payload["event"]["channel"]
    thread_ts = payload["event"].get("thread_ts") or payload["event"].get("ts")

    async with AsyncSessionLocal() as db:
        try:
            gateway = ChannelGateway(db)
            try:
                decision = await gateway.route_message(msg)
            except PermissionDeniedError:
                # Unknown or inactive channel — silently ignore
                logger.info("Ignoring message from unconfigured Slack channel %s", slack_channel)
                await db.commit()
                return

            permission = decision.permission_level

            if permission == PermissionLevel.read_only_chat:
                await _handle_chat(db, msg, slack_channel, thread_ts)

            elif permission == PermissionLevel.learn_candidate:
                await _handle_correction(db, msg, slack_channel, thread_ts)

            await db.commit()

        except Exception:
            await db.rollback()
            logger.exception("Error processing Slack message from channel %s", slack_channel)


async def _handle_chat(db, msg: NormalizedMessage, slack_channel: str, thread_ts: str) -> None:
    """Generate a chat response and post it as a thread reply."""
    from src.api.admin import _build_memory_context

    llm = get_llm_provider()
    memory_service = MemoryService(db=db, llm=llm)

    memories = await memory_service.retrieve_relevant(
        query=msg.content,
        limit=30,
        actor=f"slack:{msg.sender_id}",
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
- Keep answers concise — this is a chat, not an essay.

{memory_context}"""

    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=msg.content),
    ]
    response = await llm.complete(messages, max_tokens=512, temperature=0.7)

    # Persist session
    session = ChatSession(
        channel_id=msg.channel_id,
        question=msg.content,
        response=response.content,
        memories_used=len(memories),
        memory_ids=[str(m.id) for m in memories],
    )
    db.add(session)
    await db.flush()

    await send_message(
        token=settings.SLACK_BOT_TOKEN,
        channel=slack_channel,
        text=response.content,
        thread_ts=thread_ts,
    )
    logger.info("Sent chat response to Slack channel %s (session %s)", slack_channel, session.id)


async def _handle_correction(db, msg: NormalizedMessage, slack_channel: str, thread_ts: str) -> None:
    """
    Save a message from the corrections channel as a high-confidence memory.

    The sender of this channel is trusted (set via allowlist in ChannelConfig),
    so their corrections are auto-approved without admin review.
    """
    memory_service = MemoryService(db=db, llm=None)

    candidate = await memory_service.create_candidate(
        proposed_content=msg.content,
        proposed_type="idea",
        actor=f"subject:{msg.sender_id}",
        proposed_confidence=1.0,
        proposed_tags=["subject_correction", "slack"],
        metadata={
            "source": "subject_correction",
            "channel_id": msg.channel_id,
            "sender_id": msg.sender_id,
            "sender_name": msg.sender_name,
        },
    )

    item = await memory_service.approve_candidate(
        candidate_id=candidate.id,
        reviewer_id=msg.sender_id,
    )

    confirmation = "✓ Збережено до бази знань." if _looks_ukrainian(msg.content) else "✓ Saved to knowledge base."
    await send_message(
        token=settings.SLACK_BOT_TOKEN,
        channel=slack_channel,
        text=confirmation,
        thread_ts=thread_ts,
    )
    logger.info("Auto-approved correction from %s → MemoryItem %s", msg.sender_id, item.id)


def _looks_ukrainian(text: str) -> bool:
    """Quick heuristic — if the text contains Cyrillic characters, reply in Ukrainian."""
    return any("\u0400" <= ch <= "\u04ff" for ch in text)
