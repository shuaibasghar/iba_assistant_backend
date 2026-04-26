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
    Extract the first user message (text or document) from a webhook payload.

    Text: message_type, from_phone, sender_name, message_id, text, timestamp
    Document: message_type, media_id, mime_type, filename, caption, ...
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
        mtype = msg.get("type", "")

        contacts = value.get("contacts", [])
        sender_name = ""
        if contacts:
            profile = contacts[0].get("profile", {})
            sender_name = profile.get("name", "")

        base = {
            "from_phone": msg.get("from", ""),
            "sender_name": sender_name,
            "message_id": msg.get("id", ""),
            "timestamp": msg.get("timestamp", ""),
        }

        if mtype == "text":
            return {
                **base,
                "message_type": "text",
                "text": msg.get("text", {}).get("body", ""),
            }

        if mtype == "document":
            doc = msg.get("document") or {}
            media_id = doc.get("id", "")
            if not media_id:
                log.warning("WhatsApp document message missing media id")
                return None
            return {
                **base,
                "message_type": "document",
                "media_id": media_id,
                "mime_type": doc.get("mime_type", ""),
                "filename": doc.get("filename", "document.pdf"),
                "caption": (doc.get("caption") or "").strip(),
            }

        log.info("Ignoring unsupported WhatsApp message type: %s", mtype)
        return None
    except (IndexError, KeyError, TypeError) as exc:
        log.warning("Failed to parse WhatsApp webhook: %s", exc)
        return None


def graph_media_url(media_id: str) -> str:
    s = get_settings()
    return f"https://graph.facebook.com/{s.whatsapp_api_version}/{media_id}"


def download_whatsapp_media(media_id: str) -> tuple[bytes, str]:
    """Download file bytes for a WhatsApp Cloud API media id."""
    if not is_configured():
        raise RuntimeError("WhatsApp API not configured")

    token = get_settings().whatsapp_api_token
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=90) as client:
        r = client.get(graph_media_url(media_id), headers=headers)
        r.raise_for_status()
        meta = r.json()
        url = meta.get("url")
        mime = meta.get("mime_type", "application/octet-stream")
        if not url:
            raise RuntimeError("No download URL in media response")
        r2 = client.get(url, headers=headers)
        r2.raise_for_status()
        return r2.content, mime


def pick_whatsapp_phone(user_doc: dict) -> Optional[str]:
    """First usable phone from a Mongo user document (digits, no +/spaces)."""
    for field in ("whatsapp_number", "phone", "contact_number", "mobile"):
        raw = (user_doc.get(field) or "").strip()
        if raw:
            return raw.lstrip("+").replace(" ", "").replace("-", "")
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
