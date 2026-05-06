"""
WhatsApp channel adapter (stub).

Translates WhatsApp Cloud API webhook payloads into NormalizedMessage objects.
"""

import logging
from typing import Any

from src.channels.gateway import NormalizedMessage

logger = logging.getLogger(__name__)


def normalize_whatsapp_event(payload: dict[str, Any]) -> NormalizedMessage:
    """
    Convert a WhatsApp Cloud API webhook payload to a NormalizedMessage.

    Expected payload structure (WhatsApp Cloud API - text message):
      {
        "object": "whatsapp_business_account",
        "entry": [{
          "id": "WABA_ID",
          "changes": [{
            "value": {
              "messaging_product": "whatsapp",
              "metadata": {"phone_number_id": "PHONE_ID"},
              "contacts": [{"profile": {"name": "Alice"}, "wa_id": "1234567890"}],
              "messages": [{
                "id": "wamid.xxx",
                "from": "1234567890",
                "type": "text",
                "text": {"body": "Hello"}
              }]
            }
          }]
        }]
      }

    This is a stub — production implementation must also:
    - Verify the X-Hub-Signature-256 header
    - Handle media messages (image, audio, document)
    - De-duplicate by message ID
    """
    try:
        change_value = payload["entry"][0]["changes"][0]["value"]
        message = change_value["messages"][0]
        contact = change_value.get("contacts", [{}])[0]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Malformed WhatsApp payload: {exc}") from exc

    if message.get("type") != "text":
        raise ValueError(f"Unsupported WhatsApp message type: {message.get('type')!r}")

    phone_number_id = change_value.get("metadata", {}).get("phone_number_id", "")
    sender_id = message.get("from", "")
    sender_name = contact.get("profile", {}).get("name", "")
    content = message.get("text", {}).get("body", "")
    message_id = message.get("id", "")

    return NormalizedMessage(
        channel_id=f"whatsapp:{phone_number_id}",
        channel_type="whatsapp",
        sender_id=sender_id,
        sender_name=sender_name,
        content=content,
        message_id=message_id,
        raw_payload=payload,
    )
