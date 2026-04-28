"""
Chat API Router
================
FastAPI endpoints for the chat service.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List
import json
from services.chat_service import ChatService, get_chat_service, ChatResponse

# Optional: Vector store (requires langchain-chroma)
try:
    from services.vector_store import get_vector_store_manager
    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False
    get_vector_store_manager = None


router = APIRouter(prefix="/chat", tags=["Chat"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════════════════════

class StartSessionRequest(BaseModel):
    """Request to start a new chat session."""
    student_id: Optional[str] = Field(None, description="MongoDB ObjectId (student, teacher, or admin doc)")
    roll_number: Optional[str] = Field(None, description="Student roll number or staff employee_id")
    email: Optional[str] = Field(None, description="User email")
    user_role: Optional[str] = Field(
        None,
        description="Must match JWT role: student | teacher | admin | superadmin (strongly recommended)",
    )
    tenant_id: str = Field("default", description="Tenant/University ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "roll_number": "CS-2023-001",
                "tenant_id": "iba_sukkur"
            }
        }


class SessionResponse(BaseModel):
    """Response with session details."""
    session_id: str
    student_name: str
    roll_number: str
    email: str
    semester: int
    department: str
    user_role: str
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "abc123...",
                "student_name": "Ali Khan",
                "roll_number": "CS-2023-001",
                "email": "ali.khan@iba-suk.edu.pk",
                "semester": 3,
                "department": "CS",
                "user_role": "student",
                "message": "Welcome Ali Khan! How can I help you today?"
            }
        }


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""
    session_id: str = Field(..., description="Session ID from start_session")
    message: str = Field(..., description="User's message", min_length=1, max_length=2000)
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "abc123...",
                "message": "meri fees ka status batao"
            }
        }


class ChatMessageResponse(BaseModel):
    """Response from chat."""
    session_id: str
    message: str
    intent: str
    student_name: str
    timestamp: str
    processing_time_ms: float
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "abc123...",
                "message": "Your current semester fee status is UNPAID...",
                "intent": "FEE",
                "student_name": "Ali Khan",
                "timestamp": "2024-01-15T10:30:00",
                "processing_time_ms": 1234.56
            }
        }


class ChatHistoryResponse(BaseModel):
    """Chat history response."""
    session_id: str
    messages: List[dict]
    count: int


class EndSessionResponse(BaseModel):
    """Response when ending session."""
    success: bool
    message: str


# ═══════════════════════════════════════════════════════════════════════════════
# Dependency
# ═══════════════════════════════════════════════════════════════════════════════

def get_service() -> ChatService:
    """Dependency to get chat service."""
    return get_chat_service()


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/session/start", response_model=SessionResponse)
async def start_session(
    request: StartSessionRequest,
    service: ChatService = Depends(get_service)
):
    """
    Start a new chat session for a student, teacher, or admin.
    
    Provide one of: student_id, roll_number, or email. Pass ``user_role`` matching
    the logged-in JWT role so the correct MongoDB collection is used.
    
    Session expires after 30 minutes of inactivity.
    """

    # print(
    #     "Start Session Request:\n"
    #     + json.dumps(request.model_dump(), indent=2, ensure_ascii=False)
    # )
    if not any([request.student_id, request.roll_number, request.email]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: student_id, roll_number, or email"
        )
    
    session = service.start_session(
        student_id=request.student_id,
        roll_number=request.roll_number,
        email=request.email,
        tenant_id=request.tenant_id,
        hint_role=request.user_role,
    )
    # if session is None:
    #     print("Start Session (service result): null")
    # else:
    #     print(
    #         "Start Session (service result):\n"
    #         + json.dumps(session.to_dict(), indent=2, ensure_ascii=False)
    #     )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="User not found. Use credentials registered in the portal and pass user_role (student | teacher | admin | superadmin) matching your login."
        )
    
    role = (session.user_role or "").strip().lower()
    if role in ("superadmin", "superuser"):
        start_message = (
            f"System console ready, {session.student_name}. "
            "Org-wide and escalations are in scope; student self-service (fees, personal grades) is not."
        )
    else:
        start_message = f"Welcome {session.student_name}! How can I help you today?"
    return SessionResponse(
        session_id=session.session_id,
        student_name=session.student_name,
        roll_number=session.roll_number,
        email=session.email,
        semester=session.semester,
        department=session.department,
        user_role=session.user_role,
        message=start_message,
    )


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: ChatMessageRequest,
    service: ChatService = Depends(get_service)
):
    """
    Send a message and get AI response.
    
    The system will:
    1. Detect your intent (assignment, fee, exam, grade, document)
    2. Route to the appropriate specialist agent
    3. Query the database for your information
    4. Return a natural language response
    
    Supports both English and Roman Urdu queries.
    """
    response = service.chat(
        session_id=request.session_id,
        message=request.message
    )
    
    if response.intent == "ERROR":
        raise HTTPException(
            status_code=401,
            detail=response.message
        )
    
    return ChatMessageResponse(
        session_id=response.session_id,
        message=response.message,
        intent=response.intent,
        student_name=response.student_name,
        timestamp=response.timestamp,
        processing_time_ms=response.processing_time_ms
    )


@router.get("/session/{session_id}/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    service: ChatService = Depends(get_service)
):
    """
    Get chat history for a session.
    
    Returns all messages exchanged in the current session.
    """
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired"
        )
    
    messages = service.get_chat_history(session_id)
    
    return ChatHistoryResponse(
        session_id=session_id,
        messages=messages,
        count=len(messages)
    )


@router.get("/session/{session_id}/status")
async def get_session_status(
    session_id: str,
    service: ChatService = Depends(get_service)
):
    """
    Check session status and remaining time.
    """
    session = service.get_session(session_id)
    if not session:
        return {
            "valid": False,
            "message": "Session not found or expired"
        }
    
    ttl = service.session_manager.get_session_ttl(session_id)
    
    return {
        "valid": True,
        "session_id": session_id,
        "student_name": session.student_name,
        "roll_number": session.roll_number,
        "remaining_seconds": ttl,
        "remaining_minutes": round(ttl / 60, 1)
    }


@router.post("/session/{session_id}/end", response_model=EndSessionResponse)
async def end_session(
    session_id: str,
    service: ChatService = Depends(get_service)
):
    """
    End a chat session (logout).
    
    Clears session data and conversation history.
    """
    success = service.end_session(session_id)
    
    if success:
        return EndSessionResponse(
            success=True,
            message="Session ended successfully. Goodbye!"
        )
    else:
        return EndSessionResponse(
            success=False,
            message="Session was already expired or not found."
        )


@router.post("/session/{session_id}/refresh")
async def refresh_session(
    session_id: str,
    service: ChatService = Depends(get_service)
):
    """
    Refresh session to extend TTL.
    
    Call this periodically to keep the session alive.
    """
    success = service.session_manager.refresh_session(session_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired"
        )
    
    ttl = service.session_manager.get_session_ttl(session_id)
    
    return {
        "success": True,
        "message": "Session refreshed",
        "remaining_seconds": ttl
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Vector Search Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class SemanticSearchRequest(BaseModel):
    """Request for semantic search."""
    query: str = Field(..., description="Search query", min_length=1)
    collection: str = Field("assignments", description="Collection to search: 'courses' or 'assignments'")
    limit: int = Field(5, ge=1, le=20, description="Number of results")


@router.post("/search/semantic")
async def semantic_search(request: SemanticSearchRequest):
    """
    Perform semantic search over courses or assignments.
    
    Useful for finding content by meaning, not exact keywords.
    
    Examples:
    - "machine learning" → finds ML/AI related courses and assignments
    - "database design" → finds database-related content
    """
    if not VECTOR_STORE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Semantic search not available. Install langchain-chroma: pip install langchain-chroma"
        )
    
    try:
        manager = get_vector_store_manager()
        
        if request.collection == "courses":
            results = manager.search_courses(request.query, k=request.limit)
        elif request.collection == "assignments":
            results = manager.search_assignments(request.query, k=request.limit)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown collection: {request.collection}. Use 'courses' or 'assignments'."
            )
        
        return {
            "query": request.query,
            "collection": request.collection,
            "results": results,
            "count": len(results)
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search error: {str(e)}"
        )


@router.post("/search/index")
async def index_vector_data():
    """
    Index all data for semantic search.
    
    Run this after adding new courses or assignments to enable semantic search.
    """
    if not VECTOR_STORE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Semantic search not available. Install langchain-chroma: pip install langchain-chroma"
        )
    
    try:
        manager = get_vector_store_manager()
        result = manager.index_all()
        
        return {
            "success": True,
            "message": "Indexing complete",
            **result
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Indexing error: {str(e)}"
        )


from fastapi import File, UploadFile, Form
from config import get_settings
from services.pdf_assignment_extract import _extract_pdf_text
from services.document_analyzer import handle_document_upload

@router.post("/upload_file")
async def chat_file_upload_endpoint(
    request: Request,
    session_id: str = Form(...),
    file: UploadFile = File(...),
    service: ChatService = Depends(get_service)
):
    """
    Agentic File Upload:
    Whenever a file is sent in chat, it extracts its data using NLP
    to figure out what this document is, sends a summary response,
    and if it's assignment-related + uploader is a teacher → emails
    enrolled students automatically.
    """
    body = await file.read()

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported for agent extraction right now.")

    try:
        text = _extract_pdf_text(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF text: {str(e)}")

    if not text.strip():
        return {
            "success": True,
            "message": "I received the file, but it appears to be empty or an image-based PDF that I couldn't read."
        }

    # Get session to know who uploaded (teacher / student / admin)
    session = service.get_session(session_id)
    user_role = "student"
    user_id = ""
    user_name = "Unknown"
    if session:
        user_role = session.user_role
        user_id = session.student_id      # stores Mongo _id for any role
        user_name = session.student_name

    settings = get_settings()
    download_base = (settings.public_api_base_url or "").strip().rstrip("/")
    if not download_base:
        download_base = str(request.base_url).rstrip("/")

    # Classify header via NLP, persist full PDF, emails/WhatsApp, absolute signed download URL
    analyzer_result = handle_document_upload(
        text=text,
        filename=file.filename or "document.pdf",
        session_user_role=user_role,
        session_user_id=user_id,
        session_user_name=user_name,
        pdf_bytes=body,
        download_base_url=download_base,
    )

    classification = analyzer_result.get("classification", {})
    doc_type = classification.get("document_type", "other")
    summary = classification.get("summary", "I analysed the document.")
    key_dates = classification.get("key_dates", [])
    title = classification.get("title_hint") or file.filename

    # Build a natural-language chat reply
    notify_label = analyzer_result.get("notify_target_label", "")
    reply_parts = [f"📄 **Document:** {title}", f"**Type:** {doc_type.title()}", f"**Summary:** {summary}"]

    if key_dates:
        dates_str = ", ".join(f"{d.get('label','Date')}: {d.get('date','N/A')}" for d in key_dates)
        reply_parts.append(f"**Key Dates:** {dates_str}")

    # Assignment saved to DB?
    if analyzer_result.get("assignment_saved"):
        save_info = analyzer_result.get("assignment_save_details", {})
        cname = save_info.get("course_name", save_info.get("course_code", "?"))
        ccode = save_info.get("course_code", "")
        reply_parts.append(
            f"\n📝 Assignment published to **{cname} ({ccode})** "
            f"(due: {save_info.get('due_date', 'N/A')[:10]}). "
            f"{save_info.get('students_count', 0)} student(s) can now see it."
        )
        dl = analyzer_result.get("download_signed_url") or save_info.get("download_signed_url")
        if dl:
            reply_parts.append(f"\n🔗 **Download full assignment PDF (signed link):**\n{dl}")

    # Student submission recorded?
    if analyzer_result.get("submission_recorded"):
        sub_info = analyzer_result.get("submission_details", {})
        cname = sub_info.get("course_name", sub_info.get("course_code", "?"))
        ccode = sub_info.get("course_code", "")
        a_title = sub_info.get("assignment_title", "assignment")
        teacher = sub_info.get("teacher_name", "your teacher")
        reply_parts.append(
            f"\n📝 Submission recorded for **{a_title}** in **{cname} ({ccode})**."
        )
        if sub_info.get("submission_updated"):
            reply_parts.append("✅ Your assignment status has been updated to **submitted**.")
        dl_sub = analyzer_result.get("submission_download_signed_url") or sub_info.get(
            "student_submission_signed_url"
        )
        if dl_sub:
            reply_parts.append(f"\n🔗 **Your submitted PDF (signed link):**\n{dl_sub}")
        if sub_info.get("teacher_email"):
            reply_parts.append(f"📧 **{teacher}** will be notified about your submission.")

    if not analyzer_result.get("email_configured"):
        reply_parts.append("\n⚠️ Email notifications are not configured (SMTP credentials missing in .env).")
    elif analyzer_result.get("email_sent"):
        details = analyzer_result["email_details"]
        reply_parts.append(
            f"\n✅ Emails sent to {details['sent']} recipient(s) in **{notify_label}**."
        )
        if details.get("failed"):
            reply_parts.append(f"⚠️ {details['failed']} email(s) failed to deliver.")
    elif notify_label and notify_label != "none":
        reply_parts.append(f"\nℹ️ Identified target: **{notify_label}**, but no recipients found in the database.")

    message = "\n".join(reply_parts)

    # Also push through ChatService so this stays in conversation memory
    prompt = (
        f"I just uploaded a document named '{file.filename}'. "
        f"Please analyze the following text extracted from it, figure out what kind of document it is, "
        f"and provide a short helpful summary of its contents. If it contains dates or deadlines, list them.\n\n"
        f"--- DOCUMENT TEXT ---\n{text[:3000]}\n--- END TEXT ---"
    )
    service.chat(session_id=session_id, message=prompt)

    return {
        "success": True,
        "message": message,
    }

