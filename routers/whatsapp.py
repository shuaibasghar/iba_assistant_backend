"""
WhatsApp Webhook Router
========================
Handles incoming WhatsApp messages via Meta's Cloud API webhook.

Endpoints:
  GET  /whatsapp/webhook  — Verification (Meta calls this once during setup)
  POST /whatsapp/webhook  — Incoming messages

Flow:
  1. User sends message on WhatsApp
  2. Meta forwards it to POST /whatsapp/webhook
  3. We parse the message, find the user in our DB by phone number
  4. We create/resume a chat session and run the same AI pipeline
  5. We send the response back via WhatsApp Cloud API
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks

from config import get_settings
from services.whatsapp_service import (
    is_configured as wa_is_configured,
    parse_incoming_message,
    send_reply,
    mark_as_read,
    lookup_user_by_phone,
)
from services.chat_service import ChatService, get_chat_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# In-memory map: phone → session_id (so we can resume conversations)
_phone_sessions: dict[str, str] = {}


# ═══════════════════════════════════════════════════════════════════════
# WEBHOOK VERIFICATION (GET) — Meta calls this once during setup
# ═══════════════════════════════════════════════════════════════════════

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    WhatsApp webhook verification.

    Meta sends a GET request with:
      - hub.mode = "subscribe"
      - hub.verify_token = the token you set in Meta dashboard
      - hub.challenge = a random string

    We must return hub.challenge as plain text if the verify token matches.
    """
    settings = get_settings()

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        log.info("✅ WhatsApp webhook verified successfully")
        return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge

    log.warning("❌ WhatsApp webhook verification failed: mode=%s token=%s", hub_mode, hub_verify_token)
    raise HTTPException(status_code=403, detail="Verification failed")


# ═══════════════════════════════════════════════════════════════════════
# INCOMING MESSAGES (POST) — Meta sends every user message here
# ═══════════════════════════════════════════════════════════════════════

@router.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Receive incoming WhatsApp messages.

    Meta always expects a 200 response within 5 seconds. So we queue
    the actual AI processing in the background and reply asynchronously.
    """
    body = await request.json()

    # Meta sometimes sends status updates (delivered, read) — ignore them
    msg = parse_incoming_message(body)
    if not msg:
        return {"status": "ignored"}

    log.info(
        "📱 WhatsApp message from %s (%s): %s",
        msg["from_phone"], msg["sender_name"], msg["text"][:100],
    )

    # Process in background (Meta wants fast 200 OK)
    background_tasks.add_task(
        _process_whatsapp_message,
        from_phone=msg["from_phone"],
        sender_name=msg["sender_name"],
        message_id=msg["message_id"],
        text=msg["text"],
    )

    return {"status": "received"}


# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND PROCESSING
# ═══════════════════════════════════════════════════════════════════════

def _process_whatsapp_message(
    from_phone: str,
    sender_name: str,
    message_id: str,
    text: str,
) -> None:
    """
    Process a WhatsApp message through the existing ChatService pipeline
    and reply back via WhatsApp.

    Steps:
      1. Mark message as read (blue ticks)
      2. Look up user by phone number in MongoDB
      3. Create or resume a chat session
      4. Run the message through ChatService.chat() (intent → CrewAI → response)
      5. Send the AI response back via WhatsApp
    """
    # 1. Blue ticks
    mark_as_read(message_id)

    # 2. Look up user
    user = lookup_user_by_phone(from_phone)

    service = get_chat_service()

    # 3. Create or resume session
    session_id = _phone_sessions.get(from_phone)

    if session_id:
        # Check if session is still valid
        session = service.get_session(session_id)
        if not session:
            session_id = None  # expired

    if not session_id:
        if user:
            # Known user — create session with their identity
            session = service.start_session(
                student_id=user["user_id"],
                email=user["email"],
                hint_role=user["role"],
            )
        else:
            # Unknown user — send a registration prompt
            send_reply(
                from_phone,
                message_id,
                "👋 Assalam o Alaikum! I'm the IBA Sukkur AI Assistant.\n\n"
                "I couldn't find your phone number in our system. "
                "Please make sure your WhatsApp number is registered in your student/teacher profile.\n\n"
                "You can also use the web portal at: https://portal.iba-suk.edu.pk",
            )
            return

        if not session:
            send_reply(
                from_phone,
                message_id,
                "⚠️ Sorry, I couldn't find your profile in the university system. "
                "Please contact the admin office to register.",
            )
            return

        session_id = session.session_id
        _phone_sessions[from_phone] = session_id

        # Send welcome message on first connect
        welcome = (
            f"👋 Assalam o Alaikum, {session.student_name}!\n\n"
            f"I'm the IBA Sukkur AI Assistant on WhatsApp. "
            f"You can ask me about:\n"
            f"📝 Assignments\n💰 Fees\n📅 Exams\n📊 Grades\n"
            f"📋 Attendance\n📚 Library\n\n"
            f"Just type your question!"
        )
        send_reply(from_phone, message_id, welcome)

    # 4. Run through AI pipeline
    try:
        response = service.chat(session_id=session_id, message=text)
        reply_text = response.message
    except Exception as exc:
        log.error("WhatsApp AI processing error for %s: %s", from_phone, exc)
        reply_text = (
            "⚠️ I'm having trouble processing your request right now. "
            "Please try again in a moment."
        )

    # 5. Send reply
    send_reply(from_phone, message_id, reply_text)

    log.info(
        "📱 WhatsApp reply sent to %s | intent=%s | %d chars",
        from_phone, getattr(response, 'intent', '?'), len(reply_text),
    )


# ═══════════════════════════════════════════════════════════════════════
# STATUS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════

@router.get("/status")
async def whatsapp_status():
    """Check WhatsApp integration status."""
    settings = get_settings()
    configured = wa_is_configured()
    return {
        "configured": configured,
        "phone_number_id": settings.whatsapp_phone_number_id if configured else "not set",
        "api_version": settings.whatsapp_api_version,
        "active_sessions": len(_phone_sessions),
        "webhook_url": "/whatsapp/webhook",
        "message": "WhatsApp integration is ready" if configured else (
            "WhatsApp not configured. Set WHATSAPP_API_TOKEN and "
            "WHATSAPP_PHONE_NUMBER_ID in .env"
        ),
    }
