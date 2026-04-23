"""
Session Manager with Redis
==========================
Handles student sessions with automatic TTL expiration.
Sessions are stored in Redis for fast access and auto-cleanup.
"""

import redis
import json
import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from pymongo import MongoClient
from bson import ObjectId

from config import get_settings


@dataclass
class StudentSession:
    """Represents an active student session."""
    session_id: str
    student_id: str
    student_name: str
    roll_number: str
    email: str
    semester: int
    department: str
    batch: str
    cgpa: float
    tenant_id: str
    created_at: str
    last_active: str
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "StudentSession":
        return cls(**data)
    
    def get_context(self) -> dict:
        """Get student context for CrewAI agents."""
        return {
            "student_id": self.student_id,
            "student_name": self.student_name,
            "roll_number": self.roll_number,
            "email": self.email,
            "semester": self.semester,
            "department": self.department,
            "batch": self.batch,
            "cgpa": self.cgpa,
        }


class SessionManager:
    """
    Manages student sessions using Redis.
    
    Features:
    - Auto-expiring sessions (TTL)
    - Fast session lookup
    - Student context caching
    
    Usage:
        manager = SessionManager()
        
        # Create session on login
        session = await manager.create_session(student_id, tenant_id)
        
        # Get session for requests
        session = await manager.get_session(session_id)
        
        # Refresh TTL on activity
        await manager.refresh_session(session_id)
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_client = redis.from_url(
            self.settings.redis_url,
            decode_responses=True
        )
        self.ttl = self.settings.session_ttl_seconds
        
        # MongoDB for fetching student data
        self.mongo_client = MongoClient(self.settings.mongodb_url)
        self.db = self.mongo_client[self.settings.mongodb_database]
    
    def _get_session_key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"session:{session_id}"
    
    def _get_student_from_db(self, student_id: str) -> Optional[dict]:
        """Fetch student data from MongoDB."""
        try:
            student = self.db["students"].find_one({"_id": ObjectId(student_id)})
            return student
        except Exception:
            return None
    
    def _get_student_by_roll_number(self, roll_number: str) -> Optional[dict]:
        """Fetch student by roll number."""
        return self.db["students"].find_one({"roll_number": roll_number})
    
    def _get_student_by_email(self, email: str) -> Optional[dict]:
        """Fetch student by email."""
        return self.db["students"].find_one({"email": email})
    
    def create_session(
        self, 
        student_id: str = None,
        roll_number: str = None,
        email: str = None,
        tenant_id: str = "default"
    ) -> Optional[StudentSession]:
        """
        Create a new session for a student.
        Can lookup by student_id, roll_number, or email.
        """
        # Find student in DB
        student = None
        if student_id:
            student = self._get_student_from_db(student_id)
        elif roll_number:
            student = self._get_student_by_roll_number(roll_number)
        elif email:
            student = self._get_student_by_email(email)
        
        if not student:
            return None
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        # Create session object
        session = StudentSession(
            session_id=session_id,
            student_id=str(student["_id"]),
            student_name=student.get("full_name", "Unknown"),
            roll_number=student.get("roll_number", ""),
            email=student.get("email", ""),
            semester=student.get("semester", 1),
            department=student.get("department", ""),
            batch=student.get("batch", ""),
            cgpa=student.get("cgpa", 0.0),
            tenant_id=tenant_id,
            created_at=now,
            last_active=now,
        )
        
        # Store in Redis with TTL
        key = self._get_session_key(session_id)
        self.redis_client.setex(
            key,
            self.ttl,
            json.dumps(session.to_dict())
        )
        
        return session
    
    def get_session(self, session_id: str) -> Optional[StudentSession]:
        """Get session by ID. Returns None if expired or not found."""
        key = self._get_session_key(session_id)
        data = self.redis_client.get(key)
        
        if not data:
            return None
        
        return StudentSession.from_dict(json.loads(data))
    
    def refresh_session(self, session_id: str) -> bool:
        """
        Refresh session TTL and update last_active.
        Call this on every request to keep session alive.
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        # Update last_active
        session.last_active = datetime.now().isoformat()
        
        # Store with fresh TTL
        key = self._get_session_key(session_id)
        self.redis_client.setex(
            key,
            self.ttl,
            json.dumps(session.to_dict())
        )
        
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Manually delete a session (logout)."""
        key = self._get_session_key(session_id)
        return self.redis_client.delete(key) > 0
    
    def get_session_ttl(self, session_id: str) -> int:
        """Get remaining TTL for a session in seconds."""
        key = self._get_session_key(session_id)
        ttl = self.redis_client.ttl(key)
        return max(0, ttl)
    
    def is_session_valid(self, session_id: str) -> bool:
        """Check if session exists and is valid."""
        return self.get_session(session_id) is not None


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get singleton SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
