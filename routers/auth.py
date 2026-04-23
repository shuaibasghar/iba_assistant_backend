"""
Authentication API Router
=========================
FastAPI endpoints for login, logout, and token management.
Supports role-based access for students and teachers.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

from services.auth import (
    AuthService,
    Token,
    UserAuth,
    StudentAuth,
    TeacherAuth,
    UserRole,
    get_auth_service,
    get_current_user,
    get_current_student,
    get_current_teacher,
    require_role,
    oauth2_scheme
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login request with email and password."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password", min_length=6)
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "ali.khan@iba-suk.edu.pk",
                "password": "password123"
            }
        }


class LoginResponse(BaseModel):
    """Successful login response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    user: dict
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
                "token_type": "bearer",
                "expires_in": 1800,
                "role": "student",
                "user": {
                    "user_id": "abc123",
                    "full_name": "Ali Khan",
                    "email": "ali.khan@iba-suk.edu.pk",
                    "department": "CS",
                    "role": "student"
                }
            }
        }


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str = Field(..., description="Refresh token")


class LogoutResponse(BaseModel):
    """Logout response."""
    success: bool
    message: str


class UserResponse(BaseModel):
    """Current user info response."""
    user_id: str
    email: str
    full_name: str
    role: str
    department: str


class StudentResponse(UserResponse):
    """Student info response."""
    roll_number: str
    semester: int
    batch: str
    cgpa: float


class TeacherResponse(UserResponse):
    """Teacher info response."""
    employee_id: str
    designation: str
    courses: list


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Login with email and password.
    
    The system automatically detects user role (student/teacher/admin)
    based on the email and returns appropriate tokens.
    
    **Demo credentials:**
    - Students: use any student email with password `password123`
    - Teachers: use any teacher email with password `password123`
    
    **Returns:**
    - `access_token`: Use in Authorization header as `Bearer <token>`
    - `refresh_token`: Use to get new access token when expired
    - `role`: User's role (student/teacher/admin)
    - `user`: User profile information
    """
    user, role = auth_service.authenticate_user(
        email=request.email,
        password=request.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    tokens = auth_service.create_tokens(user, role)
    
    user_info = {
        "user_id": str(user["_id"]),
        "full_name": user.get("full_name", "Unknown"),
        "email": user.get("email", ""),
        "department": user.get("department", ""),
        "role": role
    }
    
    if role == UserRole.STUDENT.value:
        user_info.update({
            "roll_number": user.get("roll_number", ""),
            "semester": user.get("semester", 1),
            "batch": user.get("batch", ""),
            "cgpa": user.get("cgpa", 0.0)
        })
    elif role == UserRole.TEACHER.value:
        user_info.update({
            "employee_id": user.get("employee_id", ""),
            "designation": user.get("designation", ""),
            "courses": user.get("courses", [])
        })
    
    return LoginResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        role=role,
        user=user_info
    )


@router.post("/login/form", response_model=LoginResponse, include_in_schema=False)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    OAuth2 compatible login (for Swagger UI Authorize button).
    Use email as username.
    """
    user, role = auth_service.authenticate_user(
        email=form_data.username,
        password=form_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    tokens = auth_service.create_tokens(user, role)
    
    return LoginResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        role=role,
        user={
            "user_id": str(user["_id"]),
            "full_name": user.get("full_name", "Unknown"),
            "email": user.get("email", ""),
            "role": role
        }
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout and invalidate the current access token.
    
    The token will be blacklisted and cannot be used again.
    Requires valid access token in Authorization header.
    """
    success = auth_service.blacklist_token(token)
    
    return LogoutResponse(
        success=success,
        message="Successfully logged out. Token has been invalidated." if success 
                else "Logout processed."
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Get a new access token using a refresh token.
    
    Use this when your access token expires (after 30 minutes by default)
    to get a new one without requiring the user to login again.
    """
    new_tokens = auth_service.refresh_access_token(request.refresh_token)
    
    if not new_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return new_tokens


@router.get("/me", response_model=UserResponse)
async def get_me(user: UserAuth = Depends(get_current_user)):
    """
    Get current authenticated user's information.
    
    Works for any role (student/teacher/admin).
    Requires valid access token.
    """
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        department=user.department
    )


@router.get("/me/student", response_model=StudentResponse)
async def get_me_student(student: StudentAuth = Depends(get_current_student)):
    """
    Get current student's detailed information.
    
    **Requires:** Student role
    
    Returns student-specific fields like roll number, semester, CGPA.
    """
    return StudentResponse(
        user_id=student.user_id,
        email=student.email,
        full_name=student.full_name,
        role=student.role,
        department=student.department,
        roll_number=student.roll_number,
        semester=student.semester,
        batch=student.batch,
        cgpa=student.cgpa
    )


@router.get("/me/teacher", response_model=TeacherResponse)
async def get_me_teacher(teacher: TeacherAuth = Depends(get_current_teacher)):
    """
    Get current teacher's detailed information.
    
    **Requires:** Teacher role
    
    Returns teacher-specific fields like employee ID, designation, courses.
    """
    return TeacherResponse(
        user_id=teacher.user_id,
        email=teacher.email,
        full_name=teacher.full_name,
        role=teacher.role,
        department=teacher.department,
        employee_id=teacher.employee_id,
        designation=teacher.designation,
        courses=teacher.courses
    )


@router.get("/verify")
async def verify_token(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Verify if a token is valid and not blacklisted.
    
    Returns token validity status and user info.
    """
    token_data = auth_service.verify_token(token)
    
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "valid": True,
        "user_id": token_data.user_id,
        "email": token_data.email,
        "role": token_data.role
    }


@router.get("/protected/student-only")
async def student_only_route(student: StudentAuth = Depends(get_current_student)):
    """
    Example protected route - students only.
    
    This demonstrates how to protect routes for students only.
    """
    return {
        "message": f"Welcome student {student.full_name}!",
        "roll_number": student.roll_number,
        "semester": student.semester
    }


@router.get("/protected/teacher-only")
async def teacher_only_route(teacher: TeacherAuth = Depends(get_current_teacher)):
    """
    Example protected route - teachers only.
    
    This demonstrates how to protect routes for teachers only.
    """
    return {
        "message": f"Welcome teacher {teacher.full_name}!",
        "employee_id": teacher.employee_id,
        "designation": teacher.designation
    }


@router.get("/protected/staff-only")
async def staff_only_route(user: UserAuth = Depends(require_role("teacher", "admin"))):
    """
    Example protected route - teachers and admins only.
    
    This demonstrates role-based access control for multiple roles.
    """
    return {
        "message": f"Welcome staff member {user.full_name}!",
        "role": user.role
    }
