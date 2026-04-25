"""
WhatsApp Cloud API Service
===========================
Handles sending/receiving WhatsApp messages via Meta's Cloud API.

How it works:
  1. Meta sends incoming messages to our webhook: POST /whatsapp/webhook
  2. We process the message through our existing ChatService pipeline
  3. We send the AI response back via the WhatsApp Cloud API

Requirements:
  - A Meta Business account + WhatsApp Business App
  - A phone number registered in WhatsApp Business
  - WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID in .env
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from pymongo import MongoClient
from bson import ObjectId

from config import get_settings

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# CONFIG CHECK
# ═══════════════════════════════════════════════════════════════════════

def is_configured() -> bool:
    """Check if WhatsApp Cloud API credentials are present."""
    s = get_settings()
    return bool(
        s.whatsapp_api_token.strip()
        and s.whatsapp_phone_number_id.strip()
        and not s.whatsapp_api_token.startswith("EAAG...")  # skip dummy
    )


def _graph_url() -> str:
    s = get_settings()
    return (
        f"https://graph.facebook.com/{s.whatsapp_api_version}"
        f"/{s.whatsapp_phone_number_id}/messages"
    )


def _headers() -> dict[str, str]:
    s = get_settings()
    return {
        "Authorization": f"Bearer {s.whatsapp_api_token}",
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════════════════════════════════════
# SEND MESSAGES
# ═══════════════════════════════════════════════════════════════════════

def send_text_message(to_phone: str, body: str) -> dict[str, Any]:
    """
    Send a plain text message to a WhatsApp number.

    Args:
        to_phone: Recipient phone in international format (e.g. "923001234567")
        body: Message text (max ~4096 chars, auto-truncated)

    Returns:
        API response dict or error dict.
    """
    if not is_configured():
        log.warning("WhatsApp API not configured — skipping message to %s", to_phone)
        return {"success": False, "reason": "WhatsApp API not configured"}

    # WhatsApp has a 4096 char limit per text message
    if len(body) > 4096:
        body = body[:4090] + "\n..."

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(_graph_url(), json=payload, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
            log.info("✅ WhatsApp message sent → %s", to_phone)
            return {"success": True, "data": data}
    except httpx.HTTPStatusError as exc:
        log.error(
            "❌ WhatsApp API error %s → %s: %s",
            exc.response.status_code, to_phone, exc.response.text,
        )
        return {"success": False, "status": exc.response.status_code, "detail": exc.response.text}
    except Exception as exc:
        log.error("❌ WhatsApp send failed → %s: %s", to_phone, exc)
        return {"success": False, "reason": str(exc)}


def send_reply(to_phone: str, message_id: str, body: str) -> dict[str, Any]:
    """
    Send a reply (in context) to a specific incoming message.
    This threads the reply under the original message on the user's phone.
    """
    if not is_configured():
        return {"success": False, "reason": "WhatsApp API not configured"}

    if len(body) > 4096:
        body = body[:4090] + "\n..."

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "context": {"message_id": message_id},
        "text": {"preview_url": False, "body": body},
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(_graph_url(), json=payload, headers=_headers())
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
    except Exception as exc:
        log.error("❌ WhatsApp reply failed → %s: %s", to_phone, exc)
        return {"success": False, "reason": str(exc)}


def mark_as_read(message_id: str) -> None:
    """Mark an incoming message as read (blue ticks)."""
    if not is_configured():
        return

    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        with httpx.Client(timeout=10) as client:
            client.post(_graph_url(), json=payload, headers=_headers())
    except Exception:
        pass  # Non-critical


# ═══════════════════════════════════════════════════════════════════════
# PARSE INCOMING WEBHOOK
# ═══════════════════════════════════════════════════════════════════════

def parse_incoming_message(payload: dict) -> Optional[dict[str, Any]]:
    """
    Extract the first text message from a WhatsApp webhook payload.

    Returns:
        {
            "from_phone": "923001234567",
            "sender_name": "Ali Khan",
            "message_id": "wamid.xxx",
            "text": "meri fees ka status batao",
            "timestamp": "1714000000",
        }
        or None if not a user text message.
    """
    try:
        entry = payload.get("entry", [])
        if not entry:
            return None

        changes = entry[0].get("changes", [])
        if not changes:
            return None

        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        if msg.get("type") != "text":
            log.info("Ignoring non-text WhatsApp message type: %s", msg.get("type"))
            return None

        # Get sender name from contacts
        contacts = value.get("contacts", [])
        sender_name = ""
        if contacts:
            profile = contacts[0].get("profile", {})
            sender_name = profile.get("name", "")

        return {
            "from_phone": msg.get("from", ""),
            "sender_name": sender_name,
            "message_id": msg.get("id", ""),
            "text": msg.get("text", {}).get("body", ""),
            "timestamp": msg.get("timestamp", ""),
        }
    except (IndexError, KeyError, TypeError) as exc:
        log.warning("Failed to parse WhatsApp webhook: %s", exc)
        return None


# ═══════════════════════════════════════════════════════════════════════
# USER LOOKUP — map phone number to portal user
# ═══════════════════════════════════════════════════════════════════════

def lookup_user_by_phone(phone: str) -> Optional[dict[str, Any]]:
    """
    Find a student/teacher/admin by their phone number in MongoDB.

    The phone field should be stored in the user's profile.
    Falls back to searching contact_number, phone, mobile fields.

    Returns:
        {"user_id": str, "full_name": str, "email": str,
         "role": "student"|"teacher"|"admin", "department": str, ...}
        or None if not found.
    """
    s = get_settings()
    client = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    db = client[s.mongodb_database]

    # Normalize: strip +, leading zeros, spaces
    normalized = phone.lstrip("+").lstrip("0").replace(" ", "").replace("-", "")
    # Also try with country code stripped (Pakistan: 92)
    variants = {normalized}
    if normalized.startswith("92"):
        variants.add("0" + normalized[2:])     # 03001234567
        variants.add(normalized[2:])           # 3001234567
    elif normalized.startswith("0"):
        variants.add("92" + normalized[1:])    # 923001234567

    phone_fields = ["phone", "contact_number", "mobile", "whatsapp_number"]

    for collection, role in [("students", "student"), ("teachers", "teacher"), ("admins", "admin")]:
        for field in phone_fields:
            query = {field: {"$in": list(variants)}}
            user = db[collection].find_one(query)
            if user:
                result = {
                    "user_id": str(user["_id"]),
                    "full_name": user.get("full_name", ""),
                    "email": user.get("email", ""),
                    "role": role,
                    "department": user.get("department", ""),
                    "roll_number": user.get("roll_number", ""),
                    "semester": user.get("semester", 0),
                    "batch": user.get("batch", ""),
                    "employee_id": user.get("employee_id", ""),
                }
                return result

    return None
