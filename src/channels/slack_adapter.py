"""
Slack channel adapter.

Responsibilities:
  - Verify Slack request signatures (replay-attack protection).
  - Normalize Slack Events API payloads → NormalizedMessage.
  - Send messages back to Slack channels/threads.

Credentials are injected from settings — never hard-coded here.
"""

import hashlib
import hmac
import logging
import time
from typing import Any, Optional

from src.channels.gateway import NormalizedMessage

_AUDIO_MIMETYPES = frozenset({
    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp3",
    "audio/mp4", "audio/wav", "audio/x-m4a", "audio/aac",
})

logger = logging.getLogger(__name__)

# Reject events with a timestamp older than this (seconds) to block replay attacks.
_MAX_TIMESTAMP_DELTA = 60 * 5


def verify_slack_signature(
    signing_secret: str,
    body: bytes,
    timestamp: str,
    signature: str,
) -> bool:
    """
    Validate the X-Slack-Signature header using HMAC-SHA256.

    Returns False (rather than raising) so callers can return HTTP 403
    without leaking internals.
    """
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - ts) > _MAX_TIMESTAMP_DELTA:
        logger.warning("Slack request timestamp too old: %s", timestamp)
        return False

    base = f"v0:{timestamp}:{body.decode('utf-8')}".encode()
    expected = "v0=" + hmac.new(
        signing_secret.encode(), base, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def normalize_slack_event(payload: dict[str, Any]) -> NormalizedMessage:
    """
    Convert a Slack Events API message event to a NormalizedMessage.

    Filters out bot messages and message-changed subtypes before this is called —
    see the event handler in src/api/slack.py.
    """
    event = payload.get("event", {})

    channel_id = event.get("channel", "")
    sender_id = event.get("user", "")
    content = event.get("text", "")
    message_id = event.get("ts", "")
    sender_name = event.get("username", "")

    if not channel_id or not sender_id:
        raise ValueError("Slack payload missing required fields: channel, user")

    files = event.get("files", [])

    return NormalizedMessage(
        channel_id=f"slack:{channel_id}",
        channel_type="slack",
        sender_id=sender_id,
        sender_name=sender_name,
        content=content,
        message_id=message_id,
        raw_payload=payload,
        files=files,
    )


def get_audio_file(msg: NormalizedMessage) -> Optional[dict]:
    """Return the first audio file attachment from a NormalizedMessage, or None."""
    for f in msg.files:
        if f.get("mimetype", "") in _AUDIO_MIMETYPES:
            return f
    return None


async def download_slack_file(url: str, token: str) -> bytes:
    """Download a private Slack file using bot token authentication."""
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=True,
            timeout=60.0,
        )
        response.raise_for_status()
        return response.content


async def send_message(
    token: str,
    channel: str,
    text: str,
    thread_ts: Optional[str] = None,
) -> None:
    """
    Post a message to a Slack channel, optionally as a thread reply.

    Uses the slack_sdk WebClient (async-compatible via run_in_executor is not
    needed — WebClient.chat_postMessage is synchronous but fast; we call it
    directly since it doesn't block the event loop for meaningful time).
    """
    import ssl
    import certifi
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    client = WebClient(token=token, ssl=ssl_context)
    try:
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        client.chat_postMessage(**kwargs)
    except SlackApiError as exc:
        logger.error(
            "Slack API error posting to channel=%s: %s",
            channel,
            exc.response["error"],
        )
