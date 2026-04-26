"""
Teacher PDF assignment upload: persist file, Mongo assignment doc, student submission stubs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from bson import ObjectId
from jose import jwt
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


def get_submission_upload_dir() -> Path:
    s = get_settings()
    base = get_backend_dir()
    d = base / s.submission_upload_subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_pdf_name(original: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(original).name).strip("._-") or "brief.pdf"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base[:120]


def verify_pdf_magic(header: bytes) -> bool:
    return len(header) >= 4 and header[:4] == b"%PDF"


def mint_assignment_download_token(user_id: str, role: str, assignment_id: str) -> str:
    """JWT for time-limited assignment PDF download (?token=) without Bearer header."""
    s = get_settings()
    # Numeric exp only — python-jose is unreliable with timezone-aware datetime in some versions
    exp_ts = int(
        (
            datetime.now(timezone.utc)
            + timedelta(hours=s.assignment_download_token_expire_hours)
        ).timestamp()
    )
    payload = {
        "sub": str(user_id),
        "role": str(role).lower(),
        "assignment_id": str(assignment_id),
        "purpose": "assignment_download",
        "exp": exp_ts,
    }
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def build_assignment_document(
    *,
    aid: ObjectId,
    course: dict[str, Any],
    course_code: str,
    title: str,
    description: str,
    teacher_oid: ObjectId,
    total_marks: int,
    due_date: datetime,
    opens_at: datetime | None,
    source: str,
    university: str | None = None,
    now: datetime | None = None,
    attachment_original_name: str | None = None,
    attachment_stored_name: str | None = None,
    attachment_mime: str | None = None,
) -> dict[str, Any]:
    """
    Canonical assignment row for MongoDB. Always sets opens_at (defaults to now),
    semester from course, is_past, created_at, is_active, university.
    Attachment fields are only added when both stored name and original name are provided.
    """
    now = now or datetime.now(timezone.utc)
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    eff_opens = opens_at or now
    if eff_opens.tzinfo is None:
        eff_opens = eff_opens.replace(tzinfo=timezone.utc)

    uni = university if university is not None else course.get("university")
    if not uni or not str(uni).strip():
        uni = "IBA Sukkur"
    else:
        uni = str(uni).strip()

    tit = (title or "").strip() or "Assignment"
    desc = (description or "").strip() or "See the attached PDF for full instructions."

    doc: dict[str, Any] = {
        "_id": aid,
        "course_id": course["_id"],
        "course_code": course_code,
        "title": tit,
        "description": desc,
        "created_by_teacher": teacher_oid,
        "total_marks": int(total_marks),
        "due_date": due_date,
        "opens_at": eff_opens,
        "is_past": due_date < now,
        "is_active": True,
        "semester": course.get("semester"),
        "created_at": now,
        "university": uni,
        "source": source,
    }
    if attachment_stored_name and attachment_original_name:
        doc["attachment_original_name"] = attachment_original_name
        doc["attachment_stored_name"] = attachment_stored_name
        doc["attachment_mime"] = attachment_mime or "application/pdf"
    return doc


def insert_pending_submissions_for_assignment(
    db,
    *,
    assignment_id: ObjectId,
    course_id: ObjectId,
    course_code: str,
    teacher_oid: ObjectId,
    out_of: int,
    university: str,
) -> int:
    """One pending row per actively enrolled student. Returns count inserted."""
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
    subs: list[dict[str, Any]] = []
    for sid in student_ids:
        st = students.get(str(sid))
        if not st:
            continue
        subs.append(
            {
                "assignment_id": assignment_id,
                "course_id": course_id,
                "course_code": course_code,
                "student_id": sid,
                "student_name": st.get("full_name", ""),
                "student_roll": st.get("roll_number", ""),
                "teacher_id": teacher_oid,
                "status": "pending",
                "submitted_at": None,
                "marks_obtained": 0,
                "out_of": int(out_of),
                "feedback": None,
                "graded": False,
                "graded_at": None,
                "is_flagged": False,
                "flag_reason": None,
                "university": university,
            }
        )
    if subs:
        db["assignment_submissions"].insert_many(subs)
    return len(subs)


# Dev-friendly default when env is empty or still has a placeholder host
_ASSIGNMENT_DOWNLOAD_BASE_FALLBACK = "http://localhost:8000"


def effective_assignment_download_base(base_override: str | None = None) -> str:
    """
    Base URL for signed assignment PDF links. Uses override, then PUBLIC_API_BASE_URL,
    ignoring common placeholder values; falls back to http://localhost:8000.
    """
    s = get_settings()
    for candidate in (
        (base_override or "").strip().rstrip("/"),
        (s.public_api_base_url or "").strip().rstrip("/"),
    ):
        if not candidate:
            continue
        low = candidate.lower()
        # Strip placeholder / template hosts (e.g. https://public.api.base.url)
        if "public.api.base" in low or "public-api-base" in low:
            continue
        return candidate
    return _ASSIGNMENT_DOWNLOAD_BASE_FALLBACK


def build_signed_assignment_url(token: str, base_override: str | None = None) -> str:
    """
    Absolute URL for assignment PDF download. Override, then settings, then localhost:8000.
    """
    q = quote(token, safe="")
    path = f"/assignments/attachment/signed?token={q}"
    base = effective_assignment_download_base(base_override)
    return f"{base}{path}"


def mint_submission_download_token(user_id: str, role: str, submission_row_id: str) -> str:
    """JWT for downloading a student's submitted work (assignment_submissions row id)."""
    s = get_settings()
    hours = int(s.submission_download_token_expire_hours)
    exp_ts = int(
        (
            datetime.now(timezone.utc)
            + timedelta(hours=hours)
        ).timestamp()
    )
    payload = {
        "sub": str(user_id),
        "role": str(role).lower(),
        "submission_id": str(submission_row_id),
        "purpose": "submission_download",
        "exp": exp_ts,
    }
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def build_signed_submission_url(token: str, base_override: str | None = None) -> str:
    q = quote(token, safe="")
    path = f"/assignments/submission/signed?token={q}"
    base = effective_assignment_download_base(base_override)
    return f"{base}{path}"


def resolve_submission_pdf_path(submission_row_id: str) -> tuple[Path, dict]:
    db = _db()
    try:
        sid = ObjectId(submission_row_id)
    except Exception as e:
        raise ValueError("Invalid submission id") from e
    row = db["assignment_submissions"].find_one({"_id": sid})
    if not row:
        raise ValueError("Submission not found")
    rel = row.get("submission_attachment_stored_name")
    if not rel:
        raise ValueError("No PDF stored for this submission")
    p = get_submission_upload_dir() / str(rel)
    if not p.is_file():
        raise ValueError("Submission file missing on server")
    return p, row


def assert_student_can_access_submission(student_id: str, sub: dict) -> None:
    try:
        sid = ObjectId(student_id)
    except Exception:
        raise PermissionError("Invalid student")
    doc_sid = sub.get("student_id")
    if doc_sid == sid:
        return
    try:
        if ObjectId(str(doc_sid)) == sid:
            return
    except Exception:
        pass
    raise PermissionError("Not your submission")


def grade_submission_for_teacher(
    teacher_id: str,
    marks_obtained: float,
    feedback: str | None = None,
    *,
    submission_id: str | None = None,
    assignment_id: str | None = None,
    student_roll: str | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible alias for :func:`services.portal_update_service.portal_record_update`
    (assignment_submission / grade). Permission: instructor on the submission row.
    """
    from services.portal_update_service import portal_record_update

    return portal_record_update(
        actor_role="teacher",
        actor_user_id=teacher_id,
        entity="assignment_submission",
        operation="grade",
        lookup={
            "submission_id": submission_id,
            "assignment_id": assignment_id,
            "student_roll": student_roll,
        },
        payload={"marks_obtained": marks_obtained, "feedback": feedback},
        confirmed=True,
    )


def assert_teacher_can_access_submission(teacher_id: str, sub: dict) -> None:
    try:
        tid = ObjectId(teacher_id)
    except Exception:
        raise PermissionError("Invalid teacher")
    cbt = sub.get("teacher_id")
    if cbt is None:
        raise PermissionError("No teacher on submission record")
    try:
        if isinstance(cbt, ObjectId):
            ok = cbt == tid
        else:
            ok = ObjectId(str(cbt)) == tid
    except Exception:
        ok = str(cbt) == str(tid)
    if not ok:
        raise PermissionError("Not the instructor for this submission")


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

    doc = build_assignment_document(
        aid=aid,
        course=course,
        course_code=course_code,
        title=title,
        description=description,
        teacher_oid=oid_teacher,
        total_marks=total_marks,
        due_date=due_date,
        opens_at=effective_opens,
        source="pdf_upload",
        university=university,
        now=now,
        attachment_original_name=_safe_pdf_name(original_filename),
        attachment_stored_name=stored_rel,
        attachment_mime="application/pdf",
    )
    db["assignments"].insert_one(doc)

    n_subs = insert_pending_submissions_for_assignment(
        db,
        assignment_id=aid,
        course_id=course_id,
        course_code=course_code,
        teacher_oid=oid_teacher,
        out_of=int(total_marks),
        university=doc["university"],
    )

    return {
        "assignment_id": str(aid),
        "course_code": course_code,
        "title": doc["title"],
        "due_date": due_date.isoformat(),
        "opens_at": doc["opens_at"].isoformat(),
        "students_notified": n_subs,
        "attachment_stored_name": stored_rel,
    }


def _teacher_owns_assignment(assignment: dict[str, Any], teacher_oid: ObjectId) -> bool:
    cbt = assignment.get("created_by_teacher")
    if cbt is None:
        return False
    try:
        if isinstance(cbt, ObjectId):
            return cbt == teacher_oid
        return ObjectId(str(cbt)) == teacher_oid
    except Exception:
        return str(cbt) == str(teacher_oid)


def _serialize_submission_row(
    s: dict[str, Any],
    *,
    teacher_user_id: str | None = None,
) -> dict[str, Any]:
    sa = s.get("submitted_at")
    ga = s.get("graded_at")
    has_pdf = bool(s.get("submission_attachment_stored_name"))
    out: dict[str, Any] = {
        "submission_id": str(s["_id"]),
        "student_id": str(s["student_id"]),
        "student_name": s.get("student_name"),
        "student_roll": s.get("student_roll"),
        "status": s.get("status"),
        "submitted_at": sa.isoformat() if sa else None,
        "graded": bool(s.get("graded")),
        "graded_at": ga.isoformat() if ga else None,
        "marks_obtained": s.get("marks_obtained"),
        "out_of": s.get("out_of"),
        "has_submission_pdf": has_pdf,
        "feedback": s.get("feedback"),
        # Student's turned-in PDF (not the assignment brief). Only when caller is the instructor.
        "submitted_work_pdf_url": None,
    }
    if teacher_user_id and has_pdf:
        try:
            tok = mint_submission_download_token(
                str(teacher_user_id), "teacher", str(s["_id"])
            )
            out["submitted_work_pdf_url"] = build_signed_submission_url(tok, None)
        except Exception:
            out["submitted_work_pdf_url"] = None
    return out


def teacher_submissions_overview(
    teacher_id: str,
    assignment_id: str | None = None,
) -> dict[str, Any]:
    """
    All submission rows for assignments created by this teacher.
    If assignment_id is set, returns that task only (must belong to the teacher).
    """
    db = _db()
    try:
        tid = ObjectId(teacher_id)
    except Exception as e:
        raise ValueError("Invalid teacher id") from e
    teacher = db["teachers"].find_one({"_id": tid})
    if not teacher:
        raise ValueError("Teacher not found")

    if assignment_id:
        try:
            aid = ObjectId(assignment_id)
        except Exception as e:
            raise ValueError("Invalid assignment id") from e
        a = db["assignments"].find_one({"_id": aid})
        if not a or not _teacher_owns_assignment(a, tid):
            raise PermissionError("Not your assignment")
        subs = list(
            db["assignment_submissions"]
            .find({"assignment_id": aid})
            .sort([("student_name", 1)])
        )
        return {
            "assignment_id": str(aid),
            "title": a.get("title"),
            "course_code": a.get("course_code"),
            "submissions": [
                _serialize_submission_row(s, teacher_user_id=teacher_id) for s in subs
            ],
            "count": len(subs),
        }

    assigns = list(
        db["assignments"]
        .find(
            {
                "$or": [
                    {"created_by_teacher": tid},
                    {"created_by_teacher": str(tid)},
                ]
            }
        )
        .sort("due_date", -1)
        .limit(80)
    )
    blocks: list[dict[str, Any]] = []
    for a in assigns:
        aid = a["_id"]
        subs = list(
            db["assignment_submissions"].find({"assignment_id": aid}).sort(
                [("student_name", 1)]
            )
        )
        blocks.append(
            {
                "assignment_id": str(aid),
                "title": a.get("title"),
                "course_code": a.get("course_code"),
                "due_date": a["due_date"].isoformat() if a.get("due_date") else None,
                "submissions": [
                    _serialize_submission_row(s, teacher_user_id=teacher_id) for s in subs
                ],
            }
        )
    return {
        "teacher_name": teacher.get("full_name"),
        "assignments": blocks,
        "assignment_count": len(blocks),
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
                "has_pdf_attachment": assignment_has_downloadable_pdf(a),
                "submission_status": sub.get("status") if sub else "pending",
                "source": a.get("source"),
            }
        )
    return out


def _heal_assignment_pdf_metadata(doc: dict | None) -> dict | None:
    """
    If `uploads/assignments/{_id}.pdf` exists but Mongo has no (or broken)
    attachment_stored_name, backfill metadata so downloads and listings work.
    """
    if not doc or doc.get("_id") is None:
        return doc
    aid = doc["_id"]
    upload_dir = get_upload_dir()
    stored = doc.get("attachment_stored_name")
    if stored:
        path = upload_dir / str(stored)
        if path.is_file():
            return doc
    canonical = upload_dir / f"{aid}.pdf"
    if not canonical.is_file():
        return doc
    rel = f"{aid}.pdf"
    patch: dict[str, Any] = {
        "attachment_stored_name": rel,
        "attachment_mime": "application/pdf",
    }
    if not doc.get("attachment_original_name"):
        patch["attachment_original_name"] = _safe_pdf_name("assignment.pdf")
    db = _db()
    db["assignments"].update_one({"_id": aid}, {"$set": patch})
    merged = dict(doc)
    merged.update(patch)
    return merged


def _assignment_doc_if_download_ready(doc: dict) -> dict | None:
    """Heal metadata if needed; return the assignment dict if a PDF file exists, else None."""
    h = _heal_assignment_pdf_metadata(dict(doc))
    if not h or not h.get("attachment_stored_name"):
        return None
    if not (get_upload_dir() / h["attachment_stored_name"]).is_file():
        return None
    return h


def assignment_has_downloadable_pdf(doc: dict) -> bool:
    """True if a PDF exists on disk for this assignment row (heals DB metadata if needed)."""
    return _assignment_doc_if_download_ready(doc) is not None


def resolve_attachment_path(assignment_id: str) -> tuple[Path, dict]:
    db = _db()
    try:
        aid = ObjectId(assignment_id)
    except Exception as e:
        raise ValueError("Invalid assignment id") from e
    a = db["assignments"].find_one({"_id": aid})
    if not a:
        raise ValueError("Assignment not found")
    a = _heal_assignment_pdf_metadata(a)
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
    cbt = assignment.get("created_by_teacher")
    if cbt is None:
        raise PermissionError("Not your assignment")
    try:
        if isinstance(cbt, ObjectId):
            ok = cbt == tid
        else:
            ok = ObjectId(str(cbt)) == tid
    except Exception:
        ok = str(cbt) == str(tid)
    if not ok:
        raise PermissionError("Not your assignment")


def _has_pdf_attachment(doc: dict) -> bool:
    name = doc.get("attachment_stored_name")
    return bool(name and str(name).strip())


def _due_sort_key(a: dict) -> datetime:
    d = a.get("due_date")
    if d is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if getattr(d, "tzinfo", None) is None:
        return d.replace(tzinfo=timezone.utc)
    return d


def _created_sort_key(a: dict) -> datetime:
    """When the assignment row was created (upload / publish time)."""
    c = a.get("created_at")
    if c is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if getattr(c, "tzinfo", None) is None:
        return c.replace(tzinfo=timezone.utc)
    return c


def _newest_first_key(a: dict) -> tuple[datetime, datetime]:
    """Sort: newest upload first, then latest due date."""
    return (_created_sort_key(a), _due_sort_key(a))


def _assignments_student_with_pdf(db, student_oid: ObjectId) -> list[dict]:
    course_ids = [
        e["course_id"]
        for e in db["enrollments"].find({"student_id": student_oid, "status": "active"})
    ]
    if not course_ids:
        return []
    raw = list(
        db["assignments"]
        .find({"course_id": {"$in": course_ids}, "is_active": True})
        .sort("due_date", -1)
    )
    out: list[dict] = []
    for a in raw:
        ready = _assignment_doc_if_download_ready(a)
        if ready:
            out.append(ready)
    return out


def _assignments_teacher_with_pdf(db, teacher_oid: ObjectId) -> list[dict]:
    # Match ObjectId or legacy string stored in Mongo
    raw = list(
        db["assignments"]
        .find(
            {
                "$or": [
                    {"created_by_teacher": teacher_oid},
                    {"created_by_teacher": str(teacher_oid)},
                ]
            }
        )
        .sort("due_date", -1)
    )
    out: list[dict] = []
    for a in raw:
        ready = _assignment_doc_if_download_ready(a)
        if ready:
            out.append(ready)
    return out


def _rank_assignments_for_query(candidates: list[dict], search_query: str, limit: int) -> list[dict]:
    """Order by semantic match, then substring; empty query → newest uploads first."""
    sq = (search_query or "").strip()
    if not sq:
        sorted_docs = sorted(candidates, key=_newest_first_key, reverse=True)
        return sorted_docs[:limit]

    sq_l = sq.lower()
    auth_by_id = {str(a["_id"]): a for a in candidates}
    ordered_ids: list[str] = []

    # Vague asks ("pdf", "link", "bhejo", "last upload"...) don't appear in title — treat as "recent"
    vague_tokens = (
        "pdf", "link", "file", "document", "bhejo", "bhej", "download", "send",
        "last", "latest", "recent", "upload", "uploaded", "naya", "abhi", "wali", "wo",
    )
    if len(sq_l) <= 120 and any(t in sq_l for t in vague_tokens):
        sorted_docs = sorted(candidates, key=_newest_first_key, reverse=True)
        return sorted_docs[:limit]

    try:
        from services.vector_store import get_vector_store_manager

        mgr = get_vector_store_manager()
        for r in mgr.search_assignments(sq, k=40):
            aid = r.get("assignment_id")
            if aid and aid in auth_by_id and aid not in ordered_ids:
                ordered_ids.append(aid)
    except Exception:
        pass

    for a in candidates:
        aid = str(a["_id"])
        if aid in ordered_ids:
            continue
        blob = f"{a.get('title', '')} {a.get('course_code', '')} {a.get('description', '')}".lower()
        if sq_l in blob:
            ordered_ids.append(aid)

    return [auth_by_id[i] for i in ordered_ids[:limit]]


def get_authorized_portal_downloads(
    user_id: str,
    user_role: str,
    search_query: str = "",
    limit: int = 5,
    download_base: str | None = None,
) -> dict[str, Any]:
    """
    Find downloadable PDFs the user is allowed to access (course/assignment materials
    stored on the portal), optionally ranked by a natural-language query.

    Note: Official transcripts / enrollment certificates are not returned here; those
    use the records workflow. This covers shared teaching materials (assignment briefs,
    uploaded class PDFs, etc.).
    """
    role = (user_role or "").strip().lower()
    if role not in ("student", "teacher"):
        return {
            "items": [],
            "message": "Download links for course materials are available to students and teachers only.",
        }

    try:
        uid = ObjectId(user_id)
    except Exception:
        return {"items": [], "message": "Invalid user id."}

    lim = max(1, min(int(limit or 5), 10))
    db = _db()

    if role == "student":
        candidates = _assignments_student_with_pdf(db, uid)
    else:
        candidates = _assignments_teacher_with_pdf(db, uid)

    if not candidates:
        return {
            "items": [],
            "message": (
                "No PDF course materials are on file for you yet, or nothing has been uploaded "
                "to the portal for your classes."
            ),
        }

    picked = _rank_assignments_for_query(candidates, search_query, lim)
    # Ranking can return nothing for vague wording even when PDFs exist — fall back to newest
    if not picked and candidates:
        picked = sorted(candidates, key=_newest_first_key, reverse=True)[:lim]

    s = get_settings()
    base = effective_assignment_download_base(download_base)
    warn = ""

    items: list[dict[str, Any]] = []
    for a in picked:
        aid = str(a["_id"])
        try:
            if role == "student":
                assert_student_can_access_assignment(user_id, a)
            else:
                assert_teacher_can_access_assignment(user_id, a)
        except PermissionError:
            continue
        if not _has_pdf_attachment(a):
            continue
        try:
            tok = mint_assignment_download_token(user_id, role, aid)
            url = build_signed_assignment_url(tok, base_override=base or None)
        except Exception:
            continue
        title = a.get("title") or "Course material"
        cc = a.get("course_code") or ""
        items.append(
            {
                "kind": "portal_course_pdf",
                "label": f"{title}" + (f" ({cc})" if cc else ""),
                "description": "Course / assignment PDF on the portal (not a transcript or certificate).",
                "assignment_id": aid,
                "title": a.get("title"),
                "course_code": a.get("course_code"),
                "download_url": url,
            }
        )

    if not items:
        return {
            "items": [],
            "message": "Could not build download links (access denied or file missing on server).",
        }

    out: dict[str, Any] = {
        "items": items,
        "count": len(items),
        "source": "portal_course_materials",
    }
    if warn:
        out["setup_note"] = warn
    return out


def get_authorized_assignment_pdf_links(
    user_id: str,
    user_role: str,
    search_query: str = "",
    limit: int = 5,
    download_base: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias for :func:`get_authorized_portal_downloads`."""
    return get_authorized_portal_downloads(
        user_id, user_role, search_query, limit, download_base
    )
