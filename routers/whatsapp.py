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
from fastapi.responses import PlainTextResponse

from config import get_settings
from services.whatsapp_service import (
    is_configured as wa_is_configured,
    parse_incoming_message,
    send_reply,
    mark_as_read,
    lookup_user_by_phone,
    download_whatsapp_media,
)
from services.chat_service import ChatService, get_chat_service
from services.document_analyzer import handle_document_upload
from services.pdf_assignment_extract import _extract_pdf_text

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])


def _whatsapp_download_base() -> str:
    from services.assignment_upload_service import effective_assignment_download_base

    return effective_assignment_download_base(None)

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

    We must return hub.challenge as **plain text** (Content-Type: text/plain).
    A JSON/integer response can cause Meta to fail even when the token matches.
    """
    settings = get_settings()
    # Strip: .env lines often include a trailing newline, which would break a plain compare
    expect = (settings.whatsapp_verify_token or "").strip()
    got = (hub_verify_token or "").strip()

    if hub_mode == "subscribe" and got == expect and expect:
        challenge = (hub_challenge or "").strip()
        if not challenge:
            log.warning("WhatsApp verify: mode OK and token OK but missing hub.challenge")
            raise HTTPException(status_code=400, detail="Missing hub.challenge")
        log.info("WhatsApp webhook verified (challenge length=%d)", len(challenge))
        return PlainTextResponse(content=challenge, status_code=200)

    log.warning(
        "WhatsApp webhook verification failed: mode=%r len(got)=%d len(expect)=%d match=%s",
        hub_mode,
        len(got),
        len(expect),
        got == expect,
    )
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

    mtype = msg.get("message_type", "text")
    if mtype == "document":
        log.info(
            "📱 WhatsApp document from %s (%s) file=%s",
            msg["from_phone"],
            msg["sender_name"],
            msg.get("filename"),
        )
        background_tasks.add_task(
            _process_whatsapp_document,
            from_phone=msg["from_phone"],
            sender_name=msg["sender_name"],
            message_id=msg["message_id"],
            media_id=msg["media_id"],
            mime_type=msg.get("mime_type") or "",
            filename=msg.get("filename") or "document.pdf",
            caption=msg.get("caption") or "",
        )
    else:
        preview = (msg.get("text") or "")[:100]
        log.info(
            "📱 WhatsApp message from %s (%s): %s",
            msg["from_phone"],
            msg["sender_name"],
            preview,
        )
        background_tasks.add_task(
            _process_whatsapp_message,
            from_phone=msg["from_phone"],
            sender_name=msg["sender_name"],
            message_id=msg["message_id"],
            text=msg.get("text") or "",
        )

    return {"status": "received"}


# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND PROCESSING
# ═══════════════════════════════════════════════════════════════════════

def _process_whatsapp_document(
    from_phone: str,
    sender_name: str,
    message_id: str,
    media_id: str,
    mime_type: str,
    filename: str,
    caption: str,
) -> None:
    """
    Teacher/student sends a PDF on WhatsApp → download, extract text, run the same
    NLP + DB pipeline as web chat upload (assignments, submissions, emails, WhatsApp).
    """
    mark_as_read(message_id)
    user = lookup_user_by_phone(from_phone)
    if not user:
        send_reply(
            from_phone,
            message_id,
            "I couldn't find your phone in our system. Register your WhatsApp number "
            "on your IBA profile, then try again.",
        )
        return

    role = user["role"]
    if role not in ("teacher", "student"):
        send_reply(
            from_phone,
            message_id,
            "Document upload from WhatsApp is only supported for teachers and students.",
        )
        return

    try:
        file_bytes, graph_mime = download_whatsapp_media(media_id)
    except Exception as exc:
        log.error("WhatsApp media download failed: %s", exc)
        send_reply(from_phone, message_id, "Could not download your file. Please try again.")
        return

    effective_mime = (mime_type or graph_mime or "").lower()
    fn_lower = (filename or "").lower()
    if "pdf" not in effective_mime and not fn_lower.endswith(".pdf"):
        send_reply(
            from_phone,
            message_id,
            "Please send an assignment as a *PDF* file so I can read and register it.",
        )
        return

    try:
        text = _extract_pdf_text(file_bytes)
    except Exception as exc:
        log.error("WhatsApp PDF extract failed: %s", exc)
        send_reply(from_phone, message_id, f"Could not read this PDF: {exc}")
        return

    if not (text or "").strip():
        send_reply(
            from_phone,
            message_id,
            "This PDF has no readable text (it may be scanned). Use a text-based PDF or the web portal.",
        )
        return

    combined = text
    if caption.strip():
        combined = f"[Teacher/student note from WhatsApp]\n{caption.strip()}\n\n{text}"

    try:
        result = handle_document_upload(
            text=combined,
            filename=filename or "document.pdf",
            session_user_role=role,
            session_user_id=user["user_id"],
            session_user_name=user.get("full_name") or sender_name or "User",
            source_tag="whatsapp_upload",
            pdf_bytes=file_bytes,
            download_base_url=_whatsapp_download_base(),
        )
    except Exception as exc:
        log.error("WhatsApp document pipeline error: %s", exc)
        send_reply(from_phone, message_id, "Something went wrong processing your document. Try again later.")
        return

    cls = result.get("classification") or {}
    doc_type = cls.get("document_type", "other")
    summary = cls.get("summary", "")

    lines = [f"📄 Document type: *{doc_type}*", ""]
    if summary:
        lines.append(summary[:1500])
        lines.append("")

    if result.get("assignment_saved"):
        det = result.get("assignment_save_details") or {}
        lines.append(
            f"✅ Saved assignment for *{det.get('course_code', '')}* — "
            f"{det.get('students_count', 0)} students updated in the system."
        )
        ws = result.get("whatsapp_students_notified", 0)
        if ws:
            lines.append(f"📱 WhatsApp sent to {ws} students (with phone on file).")
        dl = result.get("download_signed_url") or det.get("download_signed_url")
        if dl:
            lines.append(f"🔗 Your download link (full PDF):\n{dl}")
    elif result.get("submission_recorded"):
        sub = result.get("submission_details") or {}
        if sub.get("submission_updated"):
            lines.append(
                f"✅ Submission recorded for *{sub.get('course_code', '')}*: "
                f"{sub.get('assignment_title', '')}"
            )
        else:
            lines.append(
                "⚠️ No matching pending assignment was updated. Check course code or use the portal."
            )
        dl_sub = result.get("submission_download_signed_url") or sub.get(
            "student_submission_signed_url"
        )
        if dl_sub:
            lines.append(f"🔗 Your submitted PDF:\n{dl_sub}")
        if result.get("whatsapp_teacher_notified"):
            lines.append("📱 Your teacher was notified on WhatsApp.")
    else:
        lines.append("ℹ️ No assignment/submission row was changed. If this was meant as a new task, say it's an assignment in the PDF text.")

    if result.get("email_sent"):
        lines.append("📧 Email notification sent.")
    elif result.get("email_configured") is False:
        lines.append("(Email not configured on server.)")

    send_reply(from_phone, message_id, "\n".join(lines).strip())


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
    intent = "?"
    try:
        response = service.chat(session_id=session_id, message=text)
        reply_text = response.message
        intent = getattr(response, "intent", "?")
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
        from_phone,
        intent,
        len(reply_text),
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
        "webhook_path": "/whatsapp/webhook",
        "verify_token_set": bool((settings.whatsapp_verify_token or "").strip()),
        "message": "WhatsApp integration is ready" if configured else (
            "WhatsApp not configured. Set WHATSAPP_API_TOKEN and "
            "WHATSAPP_PHONE_NUMBER_ID in .env"
        ),
    }
