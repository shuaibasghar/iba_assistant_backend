"""
Conversation Manager with LangChain
====================================
Handles conversation memory and chat history for each session.
Uses Redis-backed memory for persistence within session lifetime.
"""

import json
import logging
from typing import Optional, List
from datetime import datetime
import redis

log = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory

from config import get_settings
from .session_manager import StudentSession


class SessionChatHistory(BaseChatMessageHistory):
    """
    Custom chat history backed by Redis.
    Automatically expires with the session.
    """
    
    def __init__(self, session_id: str, redis_url: str, ttl: int = 1800):
        self.session_id = session_id
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.key = f"chat_history:{session_id}"
        self.ttl = ttl
    
    @property #this is a property of the class, so we can access it like a variable instead of calling function
    def messages(self) -> List[BaseMessage]:
        """Get all messages from Redis."""
        data = self.redis_client.get(self.key)
        if not data:
            return []
        
        messages = []
        for msg in json.loads(data):
            if msg["type"] == "human":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["type"] == "ai":
                messages.append(AIMessage(content=msg["content"]))
        
        return messages
    
    def add_message(self, message: BaseMessage) -> None:
        """Add a message and refresh TTL."""
        messages = self._get_raw_messages()
        
        msg_type = "human" if isinstance(message, HumanMessage) else "ai"
        messages.append({
            "type": msg_type,
            "content": message.content,
            "timestamp": datetime.now().isoformat()
        })
        
        self.redis_client.setex(
            self.key,
            self.ttl,
            json.dumps(messages)
        )
    
    def add_user_message(self, message: str) -> None:
        """Add a user message."""
        self.add_message(HumanMessage(content=message))
    
    def add_ai_message(self, message: str) -> None:
        """Add an AI message."""
        self.add_message(AIMessage(content=message))
    
    def _get_raw_messages(self) -> List[dict]:
        """Get raw message dicts from Redis."""
        data = self.redis_client.get(self.key)
        if not data:
            return []
        return json.loads(data)
    
    def clear(self) -> None:
        """Clear all messages."""
        self.redis_client.delete(self.key)
    
    def get_recent_messages(self, n: int = 5) -> List[BaseMessage]:
        """Get last N messages."""
        return self.messages[-n:]
    
    def get_context_string(self, n: int = 5) -> str:
        """Get recent chat history as a formatted string for context."""
        messages = self.get_recent_messages(n)
        if not messages:
            return "No previous conversation."
        
        lines = []
        for msg in messages:
            role = "Human" if isinstance(msg, HumanMessage) else "Assistant"
            lines.append(f"{role}: {msg.content}")
        
        return "\n".join(lines)


class ConversationManager:
    """
    Manages conversations using LangChain.
    
    Features:
    - Session-based chat history
    - Automatic TTL (expires with session)
    - Context window for agents
    - Memory integration with CrewAI
    
    Usage:
        manager = ConversationManager(session_id)
        
        # Add messages
        manager.add_user_message("meri fees batao")
        manager.add_ai_message("Your fees are...")
        
        # Get context for agents
        context = manager.get_conversation_context()
    """
    
    def __init__(self, session_id: str, session: StudentSession = None):
        self.settings = get_settings()
        self.session_id = session_id
        self.session = session
        
        # Initialize chat history with Redis backend
        self.chat_history = SessionChatHistory(
            session_id=session_id,
            redis_url=self.settings.redis_url,
            ttl=self.settings.session_ttl_seconds
        )
    
    def add_user_message(self, message: str) -> None:
        """Record a user message."""
        self.chat_history.add_user_message(message)
    
    def add_ai_message(self, message: str) -> None:
        """Record an AI response."""
        self.chat_history.add_ai_message(message)
    
    def add_exchange(self, user_message: str, ai_response: str) -> None:
        """Record a complete user-AI exchange."""
        self.add_user_message(user_message)
        self.add_ai_message(ai_response)
    
    def get_chat_history(self) -> List[BaseMessage]:
        """Get full chat history."""
        return self.chat_history.messages
    
    def get_recent_history(self, n: int = None) -> List[BaseMessage]:
        """Get recent N messages (defaults to config max)."""
        n = n or self.settings.max_chat_history
        return self.chat_history.get_recent_messages(n)
    
    def get_conversation_context(self) -> str:
        """
        Get conversation context as a formatted string.
        This is passed to CrewAI agents for context awareness.
        """
        return self.chat_history.get_context_string(
            n=self.settings.max_chat_history
        )
    
    def get_context_for_agent(self) -> dict:
        """
        Get full context dict for CrewAI agents.
        Includes student info + recent conversation.
        """
        context = {}
        
        # Add student context if session available
        if self.session:
            context.update(self.session.get_context())
        
        # Add conversation history
        context["conversation_history"] = self.get_conversation_context()
        context["message_count"] = len(self.chat_history.messages)
        
        return context
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.chat_history.clear()


class ConversationManagerFactory:
    """Factory for creating conversation managers."""
    
    _managers: dict = {} #memory bank
    @classmethod
    def get_manager(
        cls, #this is the class itself so we can access the class variables and methods like _managers cls is because of classmethod
        session_id: str, 
        session: StudentSession = None
    ) -> ConversationManager:
        """
        Get or create a conversation manager for a session.
        Caches managers for reuse within the same process.
        """
        if session_id not in cls._managers:
            cls._managers[session_id] = ConversationManager(
                session_id=session_id,
                session=session
            )
            print(f"[DEBUG] Added manager for session_id: {session_id}")
        
        print(f"[DEBUG] Total managers: {len(cls._managers)}")
        for sid, mgr in cls._managers.items():
            print(f"[DEBUG] {sid} -> chat_history_len:{len(mgr.chat_history.messages)}, session:{mgr.session}")
        # log.info(
        #     "[ConversationManagerFactory] session_id=%s cached_session_ids=%s count=%s",
        #     session_id,
        #     list(cls._managers.keys()),
        #     len(cls._managers),
        # )
        return cls._managers[session_id]
    
    @classmethod
    def remove_manager(cls, session_id: str) -> None:
        """Remove a cached manager (on session end)."""
        if session_id in cls._managers:
            del cls._managers[session_id]
    
    @classmethod
    def clear_all(cls) -> None:
        """Clear all cached managers."""
        print(f"[DEBUG] _managers contents: {cls._managers}")
        cls._managers.clear()

    @classmethod
    def get_all_managers(cls) -> dict:
        """Return all cached managers."""
        print(f"[DEBUG] _managers contents: {cls._managers}")
        return cls._managers.copy()
