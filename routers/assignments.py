"""
Assignments: teacher PDF upload; student list & download.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from config import get_settings
from services.auth import (
    AuthService,
    StudentAuth,
    TeacherAuth,
    get_auth_service,
    get_current_student,
    get_current_teacher,
    oauth2_scheme,
)
from services import assignment_upload_service as asvc
from services.pdf_assignment_extract import analyze_assignment_pdf

router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.get("/teacher/courses")
async def teacher_courses(teacher: TeacherAuth = Depends(get_current_teacher)):
    """Courses this teacher may post assignments to."""
    rows = asvc.teacher_course_options(teacher.user_id)
    return {"courses": rows}


@router.post("/teacher/pdf/analyze")
async def analyze_assignment_pdf_endpoint(
    _teacher: TeacherAuth = Depends(get_current_teacher),
    file: UploadFile = File(..., description="Assignment brief as PDF"),
):
    """Extract opened/closed dates and hints from PDF text (no DB write)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file (.pdf).",
        )
    settings = get_settings()
    max_b = settings.assignment_max_upload_mb * 1024 * 1024
    body = await file.read()
    if len(body) > max_b:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {settings.assignment_max_upload_mb} MB).",
        )
    if not asvc.verify_pdf_magic(body[:4096]):
        raise HTTPException(status_code=400, detail="File is not a valid PDF.")
    return analyze_assignment_pdf(body)


@router.post("/teacher/pdf", status_code=status.HTTP_201_CREATED)
async def create_assignment_pdf(
    teacher: TeacherAuth = Depends(get_current_teacher),
    file: UploadFile = File(..., description="Assignment brief as PDF"),
    course_code: str = Form(..., min_length=2, max_length=32),
    title: str = Form(..., min_length=1, max_length=200),
    description: str = Form(""),
    due_date: str = Form(..., description="ISO 8601 datetime"),
    opens_at: str | None = Form(
        None,
        description="When the assignment opens (ISO 8601); defaults to now if omitted",
    ),
    total_marks: int = Form(100, ge=1, le=1000),
):
    """
    Create a new assignment from an uploaded PDF. Enrolled students get a pending
    submission row and see the task like other assignments.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file (.pdf).",
        )
    settings = get_settings()
    max_b = settings.assignment_max_upload_mb * 1024 * 1024
    body = await file.read()
    if len(body) > max_b:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {settings.assignment_max_upload_mb} MB).",
        )
    if not asvc.verify_pdf_magic(body[:4096]):
        raise HTTPException(status_code=400, detail="File is not a valid PDF.")

    due_raw = due_date.strip().replace("Z", "+00:00")
    try:
        due_dt = datetime.fromisoformat(due_raw)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="due_date must be ISO 8601 (e.g. 2026-05-01T23:59:00).",
        )

    opens_dt: datetime | None = None
    if opens_at and opens_at.strip():
        o_raw = opens_at.strip().replace("Z", "+00:00")
        try:
            opens_dt = datetime.fromisoformat(o_raw)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="opens_at must be ISO 8601 if provided.",
            )

    try:
        result = asvc.create_assignment_from_pdf(
            teacher_id=teacher.user_id,
            course_code=course_code.strip().upper(),
            title=title,
            description=description,
            due_date=due_dt,
            opens_at=opens_dt,
            total_marks=total_marks,
            pdf_bytes=body,
            original_filename=file.filename,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.get("/student/mine")
async def my_assignments(student: StudentAuth = Depends(get_current_student)):
    """Assignments for the logged-in student (includes PDF-upload tasks)."""
    try:
        items = asvc.list_assignments_for_student(student.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"assignments": items}


@router.get("/{assignment_id}/attachment")
async def download_assignment_pdf(
    assignment_id: str,
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Download the assignment PDF. Students must be enrolled in the course;
    teachers must have created the assignment.
    """
    token_data = auth_service.verify_token(token)
    if not token_data or not token_data.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    try:
        path, doc = asvc.resolve_attachment_path(assignment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    role = (token_data.role or "").lower()
    try:
        if role == "student":
            asvc.assert_student_can_access_assignment(token_data.user_id, doc)
        elif role == "teacher":
            asvc.assert_teacher_can_access_assignment(token_data.user_id, doc)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only students and teachers may download assignment PDFs.",
            )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    fname = doc.get("attachment_original_name") or "assignment-brief.pdf"
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=fname,
    )
