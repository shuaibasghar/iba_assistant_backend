"""
Assignments: teacher PDF upload; student list & download.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field, model_validator

from config import get_settings
from services.auth import (
    AuthService,
    StudentAuth,
    TeacherAuth,
    UserAuth,
    UserRole,
    get_auth_service,
    get_current_student,
    get_current_teacher,
    oauth2_scheme,
    require_role,
)
from services import assignment_upload_service as asvc
from services.portal_update_service import portal_record_update
from services.pdf_assignment_extract import analyze_assignment_pdf

router = APIRouter(prefix="/assignments", tags=["Assignments"])
_log = logging.getLogger(__name__)


class GradeSubmissionBody(BaseModel):
    """Grade one row in assignment_submissions (teacher must own the submission)."""

    submission_id: str | None = Field(
        None,
        description="Mongo assignment_submissions._id (from roster/API)",
    )
    assignment_id: str | None = Field(
        None,
        description="Mongo assignments._id — use with student_roll if submission_id unknown",
    )
    student_roll: str | None = Field(
        None,
        description="Student roll, e.g. CS-2024-009 — use with assignment_id",
    )
    marks_obtained: float = Field(..., ge=0, description="Marks 0 .. out_of for this task")
    feedback: str | None = Field(None, max_length=8000)
    confirmed: bool = Field(
        True,
        description="Set false for a dry-run that returns needs_confirmation; true applies the grade.",
    )

    @model_validator(mode="after")
    def validate_lookup(self) -> "GradeSubmissionBody":
        sid = (self.submission_id or "").strip()
        aid = (self.assignment_id or "").strip()
        roll = (self.student_roll or "").strip()
        if sid:
            if aid or roll:
                raise ValueError("When submission_id is set, omit assignment_id and student_roll.")
            return self
        if aid and roll:
            return self
        raise ValueError("Provide submission_id, OR both assignment_id and student_roll.")


@router.post("/teacher/grade-submission")
async def teacher_grade_submission(
    body: GradeSubmissionBody,
    user: UserAuth = Depends(
        require_role(UserRole.TEACHER.value, UserRole.SUPERADMIN.value)
    ),
):
    """
    Record marks and optional feedback; sets graded=true and graded_at.
    Teachers must own the submission; superadmin may grade any submission.
    """
    try:
        return portal_record_update(
            actor_role=user.role,
            actor_user_id=user.user_id,
            entity="assignment_submission",
            operation="grade",
            lookup={
                "submission_id": (body.submission_id or "").strip() or None,
                "assignment_id": (body.assignment_id or "").strip() or None,
                "student_roll": (body.student_roll or "").strip() or None,
            },
            payload={
                "marks_obtained": body.marks_obtained,
                "feedback": body.feedback,
            },
            confirmed=body.confirmed,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/teacher/courses")
async def teacher_courses(teacher: TeacherAuth = Depends(get_current_teacher)):
    """Courses this teacher may post assignments to."""
    rows = asvc.teacher_course_options(teacher.user_id)
    return {"courses": rows}


@router.get("/teacher/submissions")
async def teacher_assignment_submissions(
    teacher: TeacherAuth = Depends(get_current_teacher),
    assignment_id: str | None = Query(
        None,
        description="Optional assignment _id to return only that task's roster",
    ),
):
    """
    Per-student submission rows for assignments this teacher created (portal + chat).
    Reflects status updates when students submit work (including PDF uploads).
    """
    try:
        return asvc.teacher_submissions_overview(teacher.user_id, assignment_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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


@router.get("/attachment/signed")
async def download_assignment_pdf_signed(
    token: str = Query(..., description="Time-limited JWT from chat/WhatsApp after upload"),
):
    """
    Download assignment PDF using a signed URL (no Authorization header).
    Token encodes user_id + role + assignment_id; must still pass enrollment/ownership checks.
    """
    s = get_settings()
    raw = (token or "").strip()
    # Query parsers sometimes turn '+' into space; JWT payload uses base64url (no '+'),
    # but repair common copy/paste damage in the signature segment
    if " " in raw and raw.count(".") == 2:
        raw = raw.replace(" ", "+")
    try:
        payload = jwt.decode(
            raw,
            s.jwt_secret_key,
            algorithms=[s.jwt_algorithm],
            options={"leeway": 120},
        )
    except JWTError as exc:
        _log.warning("Assignment download JWT rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired download link.",
        ) from exc

    if payload.get("purpose") != "assignment_download":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid download link.",
        )

    assignment_id = payload.get("assignment_id")
    user_id = payload.get("sub")
    role = (payload.get("role") or "").lower()

    if not assignment_id or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid download link.",
        )

    try:
        path, doc = asvc.resolve_attachment_path(assignment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        if role == "student":
            asvc.assert_student_can_access_assignment(user_id, doc)
        elif role == "teacher":
            asvc.assert_teacher_can_access_assignment(user_id, doc)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This link is only for students or teachers.",
            )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    fname = doc.get("attachment_original_name") or "assignment-brief.pdf"
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=fname,
        content_disposition_type="attachment",
    )


@router.get("/submission/signed")
async def download_submission_pdf_signed(
    token: str = Query(..., description="Time-limited JWT for student submission PDF"),
):
    """
    Download a PDF the student submitted for an assignment (enrolled student or course teacher).
    """
    s = get_settings()
    raw = (token or "").strip()
    if " " in raw and raw.count(".") == 2:
        raw = raw.replace(" ", "+")
    try:
        payload = jwt.decode(
            raw,
            s.jwt_secret_key,
            algorithms=[s.jwt_algorithm],
            options={"leeway": 120},
        )
    except JWTError as exc:
        _log.warning("Submission download JWT rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired download link.",
        ) from exc

    if payload.get("purpose") != "submission_download":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid download link.",
        )

    submission_id = payload.get("submission_id")
    user_id = payload.get("sub")
    role = (payload.get("role") or "").lower()

    if not submission_id or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid download link.",
        )

    try:
        path, row = asvc.resolve_submission_pdf_path(submission_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        if role == "student":
            asvc.assert_student_can_access_submission(user_id, row)
        elif role == "teacher":
            asvc.assert_teacher_can_access_submission(user_id, row)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This link is only for students or teachers.",
            )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    fname = row.get("submission_attachment_original_name") or "submission.pdf"
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=fname,
        content_disposition_type="attachment",
    )


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
        content_disposition_type="attachment",
    )
