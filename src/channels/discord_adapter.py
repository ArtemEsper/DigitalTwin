"""
Discord channel adapter (stub).

Translates Discord gateway or interaction payloads into NormalizedMessage objects.
"""

import logging
from typing import Any

from src.channels.gateway import NormalizedMessage

logger = logging.getLogger(__name__)


def normalize_discord_event(payload: dict[str, Any]) -> NormalizedMessage:
    """
    Convert a Discord MESSAGE_CREATE event payload to a NormalizedMessage.

    Expected payload structure (Discord Gateway - MESSAGE_CREATE):
      {
        "id": "message-snowflake",
        "channel_id": "channel-snowflake",
        "guild_id": "guild-snowflake",
        "content": "Hello",
        "author": {
          "id": "user-snowflake",
          "username": "alice",
          "bot": false
        }
      }

    This is a stub — production implementation must also:
    - Verify Discord interaction signature
    - Filter messages from bots (author.bot == true)
    - Handle guild vs. DM channels
    """
    author = payload.get("author", {})

    # Filter out bot messages to prevent loops
    if author.get("bot", False):
        raise ValueError("Ignoring bot message from Discord")

    channel_id = payload.get("channel_id", "")
    guild_id = payload.get("guild_id", "")
    sender_id = author.get("id", "")
    sender_name = author.get("username", "")
    content = payload.get("content", "")
    message_id = payload.get("id", "")

    if not channel_id or not sender_id:
        raise ValueError("Discord payload missing required fields: channel_id, author.id")

    # Use guild:channel as the stable channel identifier
    composite_channel_id = f"discord:{guild_id}:{channel_id}" if guild_id else f"discord:{channel_id}"

    return NormalizedMessage(
        channel_id=composite_channel_id,
        channel_type="discord",
        sender_id=sender_id,
        sender_name=sender_name,
        content=content,
        message_id=message_id,
        raw_payload=payload,
    )
