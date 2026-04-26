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
    """Represents an active chat session (student or teacher)."""
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
    user_role: str = "student"
    designation: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "StudentSession":
        data = dict(data)
        data.setdefault("user_role", "student")
        data.setdefault("designation", "")
        return cls(**data)
    
    def get_context(self) -> dict:
        """Get user context for CrewAI agents (student_id is Mongo _id for that role's document)."""
        ctx = {
            "student_id": self.student_id,
            "student_name": self.student_name,
            "roll_number": self.roll_number,
            "email": self.email,
            "semester": self.semester,
            "department": self.department,
            "batch": self.batch,
            "cgpa": self.cgpa,
            "user_role": self.user_role,
        }
        if self.user_role in ("teacher", "admin", "superadmin"):
            ctx["designation"] = self.designation
        return ctx


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
        self.mongo_client = MongoClient(
            self.settings.mongodb_url,
            serverSelectionTimeoutMS=15_000,
        )
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
    
    def _get_teacher_from_db(self, teacher_id: str) -> Optional[dict]:
        """Fetch teacher by MongoDB ObjectId."""
        try:
            return self.db["teachers"].find_one({"_id": ObjectId(teacher_id)})
        except Exception:
            return None
    
    def _get_teacher_by_employee_id(self, employee_id: str) -> Optional[dict]:
        return self.db["teachers"].find_one({"employee_id": employee_id})
    
    def _get_teacher_by_email(self, email: str) -> Optional[dict]:
        return self.db["teachers"].find_one({"email": email})
    
    def _get_admin_from_db(self, admin_id: str) -> Optional[dict]:
        try:
            return self.db["admins"].find_one({"_id": ObjectId(admin_id)})
        except Exception:
            return None
    
    def _get_admin_by_employee_id(self, employee_id: str) -> Optional[dict]:
        return self.db["admins"].find_one({"employee_id": employee_id})
    
    def _get_admin_by_email(self, email: str) -> Optional[dict]:
        return self.db["admins"].find_one({"email": email})

    def _get_superadmin_from_db(self, user_id: str) -> Optional[dict]:
        try:
            return self.db["superadmins"].find_one({"_id": ObjectId(user_id)})
        except Exception:
            return None

    def _get_superadmin_by_email(self, email: str) -> Optional[dict]:
        return self.db["superadmins"].find_one({"email": email})

    def create_session(
        self, 
        student_id: str = None,
        roll_number: str = None,
        email: str = None,
        tenant_id: str = "default",
        hint_role: Optional[str] = None,
    ) -> Optional[StudentSession]:
        """
        Create a new chat session for student, teacher, admin, or superadmin.

        ``hint_role`` should match the JWT role (student | teacher | admin | superadmin) so the
        correct collection is used. If omitted, tries student → teacher → admin → superadmin.
        """
        hr = (hint_role or "").strip().lower()
        if hr == "superuser":
            hr = "superadmin"
        student = None
        teacher = None
        admin_doc = None
        superadmin_doc = None

        def _lookup_student() -> None:
            nonlocal student
            if student_id:
                student = self._get_student_from_db(student_id)
            elif roll_number:
                student = self._get_student_by_roll_number(roll_number)
            elif email:
                student = self._get_student_by_email(email)

        def _lookup_teacher() -> None:
            nonlocal teacher
            if student_id:
                teacher = self._get_teacher_from_db(student_id)
            elif roll_number:
                teacher = self._get_teacher_by_employee_id(roll_number)
            elif email:
                teacher = self._get_teacher_by_email(email)

        def _lookup_admin() -> None:
            nonlocal admin_doc
            if student_id:
                admin_doc = self._get_admin_from_db(student_id)
            elif roll_number:
                admin_doc = self._get_admin_by_employee_id(roll_number)
            elif email:
                admin_doc = self._get_admin_by_email(email)

        def _lookup_superadmin() -> None:
            nonlocal superadmin_doc
            if student_id:
                superadmin_doc = self._get_superadmin_from_db(student_id)
            elif email:
                superadmin_doc = self._get_superadmin_by_email(email)

        if hr == "student":
            _lookup_student()
        elif hr == "teacher":
            _lookup_teacher()
        elif hr == "admin":
            _lookup_admin()
        elif hr == "superadmin":
            _lookup_superadmin()
        else:
            _lookup_student()
            if not student:
                _lookup_teacher()
            if not student and not teacher:
                _lookup_admin()
            if not student and not teacher and not admin_doc:
                _lookup_superadmin()

        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        if student:
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
                user_role="student",
                designation="",
            )
        elif teacher:
            session = StudentSession(
                session_id=session_id,
                student_id=str(teacher["_id"]),
                student_name=teacher.get("full_name", "Unknown"),
                roll_number=teacher.get("employee_id", ""),
                email=teacher.get("email", ""),
                semester=0,
                department=teacher.get("department", ""),
                batch="",
                cgpa=0.0,
                tenant_id=tenant_id,
                created_at=now,
                last_active=now,
                user_role="teacher",
                designation=teacher.get("designation", ""),
            )
        elif admin_doc:
            session = StudentSession(
                session_id=session_id,
                student_id=str(admin_doc["_id"]),
                student_name=admin_doc.get("full_name", "Unknown"),
                roll_number=admin_doc.get("employee_id", ""),
                email=admin_doc.get("email", ""),
                semester=0,
                department=admin_doc.get("department", ""),
                batch="",
                cgpa=0.0,
                tenant_id=tenant_id,
                created_at=now,
                last_active=now,
                user_role="admin",
                designation=str(admin_doc.get("role", "admin")),
            )
        elif superadmin_doc:
            session = StudentSession(
                session_id=session_id,
                student_id=str(superadmin_doc["_id"]),
                student_name=superadmin_doc.get("full_name", "Unknown"),
                roll_number=superadmin_doc.get("employee_id", "") or "superadmin",
                email=superadmin_doc.get("email", ""),
                semester=0,
                department=superadmin_doc.get("department", "") or "System",
                batch="",
                cgpa=0.0,
                tenant_id=tenant_id,
                created_at=now,
                last_active=now,
                user_role="superadmin",
                designation="Superadmin",
            )
        else:
            return None
        
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
    
    def reconfigure_connections(
        self,
        mongodb_url: str,
        mongodb_database: str,
        redis_url: str | None = None,
    ) -> None:
        """Recreate MongoDB and optionally Redis clients after settings change."""
        self.settings = get_settings()
        if self.mongo_client:
            self.mongo_client.close()
        self.mongo_client = MongoClient(mongodb_url)
        self.db = self.mongo_client[mongodb_database]
        if redis_url:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.ttl = self.settings.session_ttl_seconds


# Singleton instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get singleton SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
