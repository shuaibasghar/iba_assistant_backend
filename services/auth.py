"""
Authentication Service
======================
JWT-based authentication for the University Portal.
Supports role-based access control (Student, Teacher, Admin).
"""

import redis
from datetime import datetime, timedelta
from typing import Optional, Literal
from enum import Enum
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from pymongo import MongoClient
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from config import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login/form")


class UserRole(str, Enum):
    """User roles in the system."""
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class Token(BaseModel):
    """Token response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class TokenData(BaseModel):
    """Data extracted from token."""
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None


class UserAuth(BaseModel):
    """Base user authentication info."""
    user_id: str
    email: str
    full_name: str
    role: str
    department: str


class StudentAuth(UserAuth):
    """Student-specific authentication info."""
    roll_number: str
    semester: int
    batch: str
    cgpa: float


class TeacherAuth(UserAuth):
    """Teacher-specific authentication info."""
    employee_id: str
    designation: str
    courses: list = []


class AuthService:
    """
    Authentication service with role-based access control.
    
    Features:
    - JWT access and refresh tokens
    - Role-based authentication (student/teacher/admin)
    - Token blacklisting via Redis (for logout)
    - Password hashing with bcrypt
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_client = redis.from_url(
            self.settings.redis_url,
            decode_responses=True
        )
        self.mongo_client = MongoClient(self.settings.mongodb_url)
        self.db = self.mongo_client[self.settings.mongodb_database]
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def hash_password(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)
    
    def get_user_by_email(self, email: str) -> tuple[Optional[dict], Optional[str]]:
        """
        Find user by email across all collections.
        Returns (user_dict, role) or (None, None) if not found.
        """
        student = self.db["students"].find_one({"email": email})
        if student:
            return student, UserRole.STUDENT.value
        
        teacher = self.db["teachers"].find_one({"email": email})
        if teacher:
            return teacher, UserRole.TEACHER.value
        
        admin = self.db["admins"].find_one({"email": email})
        if admin:
            return admin, UserRole.ADMIN.value
        
        return None, None
    
    def get_user_by_id(self, user_id: str, role: str) -> Optional[dict]:
        """Find user by ID and role."""
        try:
            collection_map = {
                UserRole.STUDENT.value: "students",
                UserRole.TEACHER.value: "teachers",
                UserRole.ADMIN.value: "admins"
            }
            collection = collection_map.get(role, "students")
            return self.db[collection].find_one({"_id": ObjectId(user_id)})
        except Exception:
            return None
    
    def get_student_by_roll_number(self, roll_number: str) -> Optional[dict]:
        """Find student by roll number."""
        return self.db["students"].find_one({"roll_number": roll_number})
    
    def get_teacher_by_employee_id(self, employee_id: str) -> Optional[dict]:
        """Find teacher by employee ID."""
        return self.db["teachers"].find_one({"employee_id": employee_id})
    
    def authenticate_user(
        self, 
        email: str, 
        password: str
    ) -> tuple[Optional[dict], Optional[str]]:
        """
        Authenticate user by email and password.
        Returns (user_dict, role) or (None, None) if authentication fails.
        
        For demo: if no password field exists, accepts 'password123'.
        """
        user, role = self.get_user_by_email(email)
        
        if not user:
            return None, None
        
        stored_password = user.get("password")
        if stored_password:
            if not self.verify_password(password, stored_password):
                return None, None
        else:
            if password != "password123":
                return None, None
        
        return user, role
    
    def create_access_token(
        self, 
        data: dict, 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.settings.jwt_access_token_expire_minutes
            )
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })
        
        return jwt.encode(
            to_encode, 
            self.settings.jwt_secret_key, 
            algorithm=self.settings.jwt_algorithm
        )
    
    def create_refresh_token(
        self, 
        data: dict, 
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT refresh token."""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                days=self.settings.jwt_refresh_token_expire_days
            )
        
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh"
        })
        
        return jwt.encode(
            to_encode, 
            self.settings.jwt_secret_key, 
            algorithm=self.settings.jwt_algorithm
        )
    
    def create_tokens(self, user: dict, role: str) -> Token:
        """Create both access and refresh tokens for a user."""
        token_data = {
            "sub": str(user["_id"]),
            "email": user.get("email"),
            "role": role
        }
        
        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.settings.jwt_access_token_expire_minutes * 60,
            role=role
        )
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[TokenData]:
        """Verify and decode a JWT token."""
        if self.is_token_blacklisted(token):
            return None
        
        try:
            payload = jwt.decode(
                token, 
                self.settings.jwt_secret_key, 
                algorithms=[self.settings.jwt_algorithm]
            )
            
            if payload.get("type") != token_type:
                return None
            
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            
            return TokenData(
                user_id=user_id,
                email=payload.get("email"),
                role=payload.get("role")
            )
        except JWTError:
            return None
    
    def blacklist_token(self, token: str) -> bool:
        """Add a token to the blacklist (for logout)."""
        try:
            payload = jwt.decode(
                token, 
                self.settings.jwt_secret_key, 
                algorithms=[self.settings.jwt_algorithm],
                options={"verify_exp": False}
            )
            
            exp = payload.get("exp")
            if exp:
                ttl = max(0, int(exp - datetime.utcnow().timestamp()))
            else:
                ttl = self.settings.jwt_access_token_expire_minutes * 60
            
            key = f"blacklist:{token}"
            self.redis_client.setex(key, ttl, "1")
            return True
        except JWTError:
            return False
    
    def is_token_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted."""
        key = f"blacklist:{token}"
        return self.redis_client.exists(key) > 0
    
    def refresh_access_token(self, refresh_token: str) -> Optional[Token]:
        """Use a refresh token to get a new access token."""
        token_data = self.verify_token(refresh_token, token_type="refresh")
        
        if not token_data:
            return None
        
        user = self.get_user_by_id(token_data.user_id, token_data.role)
        if not user:
            return None
        
        return self.create_tokens(user, token_data.role)
    
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


_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get singleton AuthService instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
) -> UserAuth:
    """
    Get the current authenticated user (any role).
    Returns basic user info with role.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = auth_service.verify_token(token)
    if token_data is None:
        raise credentials_exception
    
    user = auth_service.get_user_by_id(token_data.user_id, token_data.role)
    if user is None:
        raise credentials_exception
    
    return UserAuth(
        user_id=str(user["_id"]),
        email=user.get("email", ""),
        full_name=user.get("full_name", "Unknown"),
        role=token_data.role,
        department=user.get("department", "")
    )


async def get_current_student(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
) -> StudentAuth:
    """Get current user if they are a student."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = auth_service.verify_token(token)
    if token_data is None:
        raise credentials_exception
    
    if token_data.role != UserRole.STUDENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Student role required."
        )
    
    student = auth_service.get_user_by_id(token_data.user_id, token_data.role)
    if student is None:
        raise credentials_exception
    
    return StudentAuth(
        user_id=str(student["_id"]),
        email=student.get("email", ""),
        full_name=student.get("full_name", "Unknown"),
        role=UserRole.STUDENT.value,
        department=student.get("department", ""),
        roll_number=student.get("roll_number", ""),
        semester=student.get("semester", 1),
        batch=student.get("batch", ""),
        cgpa=student.get("cgpa", 0.0)
    )


async def get_current_teacher(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
) -> TeacherAuth:
    """Get current user if they are a teacher."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = auth_service.verify_token(token)
    if token_data is None:
        raise credentials_exception
    
    if token_data.role != UserRole.TEACHER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Teacher role required."
        )
    
    teacher = auth_service.get_user_by_id(token_data.user_id, token_data.role)
    if teacher is None:
        raise credentials_exception
    
    return TeacherAuth(
        user_id=str(teacher["_id"]),
        email=teacher.get("email", ""),
        full_name=teacher.get("full_name", "Unknown"),
        role=UserRole.TEACHER.value,
        department=teacher.get("department", ""),
        employee_id=teacher.get("employee_id", ""),
        designation=teacher.get("designation", ""),
        courses=teacher.get("courses", [])
    )


def require_role(*allowed_roles: str):
    """
    Dependency factory for role-based access control.
    
    Usage:
        @router.get("/admin-only")
        async def admin_route(user: UserAuth = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}
        
        @router.get("/staff-only")
        async def staff_route(user: UserAuth = Depends(require_role("teacher", "admin"))):
            return {"message": "Staff access granted"}
    """
    async def role_checker(
        token: str = Depends(oauth2_scheme),
        auth_service: AuthService = Depends(get_auth_service)
    ) -> UserAuth:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        token_data = auth_service.verify_token(token)
        if token_data is None:
            raise credentials_exception
        
        if token_data.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}"
            )
        
        user = auth_service.get_user_by_id(token_data.user_id, token_data.role)
        if user is None:
            raise credentials_exception
        
        return UserAuth(
            user_id=str(user["_id"]),
            email=user.get("email", ""),
            full_name=user.get("full_name", "Unknown"),
            role=token_data.role,
            department=user.get("department", "")
        )
    
    return role_checker
