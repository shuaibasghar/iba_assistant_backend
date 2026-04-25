"""
Teacher PDF assignment upload: persist file, Mongo assignment doc, student submission stubs.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from config import get_settings, get_backend_dir


def _db():
    s = get_settings()
    client = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    return client[s.mongodb_database]


def get_upload_dir() -> Path:
    s = get_settings()
    base = get_backend_dir()
    d = base / s.assignment_upload_subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_pdf_name(original: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(original).name).strip("._-") or "brief.pdf"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base[:120]


def verify_pdf_magic(header: bytes) -> bool:
    return len(header) >= 4 and header[:4] == b"%PDF"


def create_assignment_from_pdf(
    teacher_id: str,
    course_code: str,
    title: str,
    description: str,
    due_date: datetime,
    total_marks: int,
    pdf_bytes: bytes,
    original_filename: str,
    university: str | None = None,
    opens_at: datetime | None = None,
) -> dict[str, Any]:
    """
    Insert assignment + save PDF + create pending submission rows for enrolled students.
    """
    db = _db()
    try:
        oid_teacher = ObjectId(teacher_id)
    except Exception as e:
        raise ValueError("Invalid teacher id") from e

    teacher = db["teachers"].find_one({"_id": oid_teacher})
    if not teacher:
        raise ValueError("Teacher not found")

    codes = teacher.get("assigned_course_codes") or []
    if course_code not in codes:
        raise PermissionError("You are not assigned to this course")

    dept = teacher.get("department")
    course = db["courses"].find_one(
        {"course_code": course_code, "department": dept, "is_active": True}
    )
    if not course:
        raise ValueError("Course not found for your department")

    course_id = course["_id"]
    now = datetime.now(timezone.utc)
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    if opens_at is not None and opens_at.tzinfo is None:
        opens_at = opens_at.replace(tzinfo=timezone.utc)
    effective_opens = opens_at or now

    aid = ObjectId()
    stored_rel = f"{aid}.pdf"
    upload_dir = get_upload_dir()
    dest = upload_dir / stored_rel
    dest.write_bytes(pdf_bytes)

    uni = university or course.get("university") or "IBA Sukkur"

    doc = {
        "_id": aid,
        "course_id": course_id,
        "course_code": course_code,
        "title": title.strip(),
        "description": description.strip()
        or "See the attached PDF for full instructions.",
        "created_by_teacher": oid_teacher,
        "total_marks": int(total_marks),
        "due_date": due_date,
        "opens_at": effective_opens,
        "is_past": due_date < now,
        "is_active": True,
        "semester": course.get("semester"),
        "created_at": now,
        "university": uni,
        "source": "pdf_upload",
        "attachment_original_name": _safe_pdf_name(original_filename),
        "attachment_stored_name": stored_rel,
        "attachment_mime": "application/pdf",
    }
    db["assignments"].insert_one(doc)

    enrollments = list(
        db["enrollments"].find(
            {"course_id": course_id, "status": "active"},
            {"student_id": 1},
        )
    )
    student_ids = [e["student_id"] for e in enrollments]
    students = {
        str(s["_id"]): s
        for s in db["students"].find({"_id": {"$in": student_ids}})
    }

    subs = []
    for sid in student_ids:
        st = students.get(str(sid))
        if not st:
            continue
        subs.append(
            {
                "assignment_id": aid,
                "course_id": course_id,
                "course_code": course_code,
                "student_id": sid,
                "student_name": st.get("full_name", ""),
                "student_roll": st.get("roll_number", ""),
                "teacher_id": oid_teacher,
                "status": "pending",
                "submitted_at": None,
                "marks_obtained": 0,
                "out_of": int(total_marks),
                "feedback": None,
                "graded": False,
                "graded_at": None,
                "is_flagged": False,
                "flag_reason": None,
                "university": uni,
            }
        )
    if subs:
        db["assignment_submissions"].insert_many(subs)

    return {
        "assignment_id": str(aid),
        "course_code": course_code,
        "title": doc["title"],
        "due_date": due_date.isoformat(),
        "opens_at": effective_opens.isoformat(),
        "students_notified": len(subs),
        "attachment_stored_name": stored_rel,
    }


def teacher_course_options(teacher_id: str) -> list[dict[str, Any]]:
    db = _db()
    try:
        t = db["teachers"].find_one({"_id": ObjectId(teacher_id)})
    except Exception:
        return []
    if not t:
        return []
    codes = t.get("assigned_course_codes") or []
    if not codes:
        return []
    dept = t.get("department")
    cur = db["courses"].find(
        {"course_code": {"$in": codes}, "department": dept, "is_active": True},
        {"course_code": 1, "course_name": 1, "semester": 1, "credit_hours": 1},
    )
    return [
        {
            "course_code": c["course_code"],
            "course_name": c.get("course_name"),
            "semester": c.get("semester"),
            "credit_hours": c.get("credit_hours"),
        }
        for c in cur
    ]


def list_assignments_for_student(student_id: str) -> list[dict[str, Any]]:
    """Student's assignments in their current semester courses, with PDF flag."""
    db = _db()
    student = db["students"].find_one({"_id": ObjectId(student_id)})
    if not student:
        raise ValueError("Student not found")
    sem = student.get("semester")
    dept = student.get("department")
    courses = list(
        db["courses"].find({"semester": sem, "department": dept, "is_active": True})
    )
    course_ids = [c["_id"] for c in courses]
    course_map = {str(c["_id"]): c for c in courses}

    assigns = list(
        db["assignments"].find({"course_id": {"$in": course_ids}, "is_active": True}).sort(
            "due_date", 1
        )
    )
    aids = [a["_id"] for a in assigns]
    subs = {
        str(s["assignment_id"]): s
        for s in db["assignment_submissions"].find(
            {"student_id": student["_id"], "assignment_id": {"$in": aids}}
        )
    }

    out = []
    for a in assigns:
        cid = str(a["course_id"])
        co = course_map.get(cid, {})
        sub = subs.get(str(a["_id"]))
        out.append(
            {
                "assignment_id": str(a["_id"]),
                "title": a.get("title"),
                "course_code": a.get("course_code"),
                "course_name": co.get("course_name"),
                "due_date": a["due_date"].isoformat() if a.get("due_date") else None,
                "total_marks": a.get("total_marks"),
                "description": (a.get("description") or "")[:500],
                "has_pdf_attachment": bool(a.get("attachment_stored_name")),
                "submission_status": sub.get("status") if sub else "pending",
                "source": a.get("source"),
            }
        )
    return out


def resolve_attachment_path(assignment_id: str) -> tuple[Path, dict]:
    db = _db()
    try:
        aid = ObjectId(assignment_id)
    except Exception as e:
        raise ValueError("Invalid assignment id") from e
    a = db["assignments"].find_one({"_id": aid})
    if not a or not a.get("attachment_stored_name"):
        raise ValueError("No PDF for this assignment")
    p = get_upload_dir() / a["attachment_stored_name"]
    if not p.is_file():
        raise ValueError("PDF file missing on server")
    return p, a


def assert_student_can_access_assignment(student_id: str, assignment: dict) -> None:
    db = _db()
    sid = ObjectId(student_id)
    course_id = assignment["course_id"]
    enr = db["enrollments"].find_one(
        {"student_id": sid, "course_id": course_id, "status": "active"}
    )
    if not enr:
        raise PermissionError("Not enrolled in this course")


def assert_teacher_can_access_assignment(teacher_id: str, assignment: dict) -> None:
    try:
        tid = ObjectId(teacher_id)
    except Exception:
        raise PermissionError("Invalid teacher")
    if assignment.get("created_by_teacher") != tid:
        raise PermissionError("Not your assignment")
