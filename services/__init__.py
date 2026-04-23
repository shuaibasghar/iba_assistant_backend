# Services Package
from .session_manager import SessionManager, StudentSession
from .conversation_manager import ConversationManager
from .chat_service import ChatService

__all__ = [
    "SessionManager",
    "StudentSession", 
    "ConversationManager",
    "ChatService",
]

# Optional: VectorStoreManager (requires langchain-chroma)
try:
    from .vector_store import VectorStoreManager
    __all__.append("VectorStoreManager")
except ImportError:
    pass
