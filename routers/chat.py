"""
Chat API Router
================
FastAPI endpoints for the chat service.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

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
    student_id: Optional[str] = Field(None, description="MongoDB ObjectId of student")
    roll_number: Optional[str] = Field(None, description="Student roll number")
    email: Optional[str] = Field(None, description="Student email")
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
    Start a new chat session for a student.
    
    Provide one of: student_id, roll_number, or email to identify the student.
    Returns session_id to use for subsequent chat messages.
    
    Session expires after 30 minutes of inactivity.
    """
    if not any([request.student_id, request.roll_number, request.email]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: student_id, roll_number, or email"
        )
    
    session = service.start_session(
        student_id=request.student_id,
        roll_number=request.roll_number,
        email=request.email,
        tenant_id=request.tenant_id
    )
    
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Student not found. Check the provided credentials."
        )
    
    return SessionResponse(
        session_id=session.session_id,
        student_name=session.student_name,
        roll_number=session.roll_number,
        email=session.email,
        semester=session.semester,
        department=session.department,
        message=f"Welcome {session.student_name}! How can I help you today?"
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
