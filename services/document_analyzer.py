"""
Document Analyzer — Smart Email Router
=======================================
Uses the LLM to classify any uploaded document and then automatically
decides WHO should receive an email notification based on the content:

  assignment      → enrolled students of the teacher's courses
  transcript      → exam office staff
  fee / challan   → finance staff
  hostel          → hostel staff
  library         → library staff
  complaint       → admin staff
  notice / other  → relevant department staff

The system figures it out — no hardcoded assumptions.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from langchain_openai import ChatOpenAI
from pymongo import MongoClient
from bson import ObjectId

from config import get_settings
from services.email_service import send_bulk_email, is_configured as smtp_is_configured

log = logging.getLogger(__name__)


def _normalize_marks_hint(raw: Any) -> int:
    try:
        n = int(float(raw))
        if 1 <= n <= 2000:
            return n
    except (TypeError, ValueError):
        pass
    return 100


def _assignment_header_text(full_text: str, max_chars: int = 3200) -> str:
    """
    Only the start of the PDF text for NLP (title, course, due date, marks).
    Avoids sending the whole brief to the classifier.
    """
    t = (full_text or "").strip()
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rstrip() + "\n\n[... remainder of document omitted for extraction ...]"


def infer_assignment_title(
    text: str,
    summary: str,
    course_code: str,
    filename: str,
) -> str:
    """LLM short title when classifier did not find a proper title."""
    settings = get_settings()
    if not (settings.openai_api_key or "").strip():
        fallback = (summary or "").strip()[:100] or filename.replace("_", " ").replace(".pdf", "")
        return (fallback or "New assignment")[:200]

    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    llm = ChatOpenAI(model=settings.openai_model, temperature=0)
    prompt = f"""Write ONE concise university assignment title (max 12 words, no quotation marks).
Course code: {course_code or "unknown"}
Filename: {filename}
Summary: {(summary or "")[:600]}
Document excerpt:
{(text or "")[:2500]}
Reply with ONLY the title line, nothing else."""
    try:
        out = (llm.invoke(prompt).content or "").strip().strip('"').strip("'")
        return (out[:200] if out else filename)[:200]
    except Exception as exc:
        log.warning("infer_assignment_title failed: %s", exc)
        return ((summary or filename)[:120] or "New assignment")[:200]


def _db():
    s = get_settings()
    client = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    return client[s.mongodb_database]


# ═══════════════════════════════════════════════════════════════════════
# 1. LLM CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

def classify_document(text: str, filename: str, uploader_role: str = "unknown") -> dict[str, Any]:
    """
    Use the LLM to figure out what the document is about and WHO
    should be notified.

    Returns a structured dict:
        {
            "document_type": "assignment"|"transcript"|"fee"|"hostel"|"library"|
                             "complaint"|"notice"|"syllabus"|"report"|"other",
            "notify_target": "students"|"exam_staff"|"finance_staff"|"hostel_staff"|
                             "library_staff"|"admin_staff"|"department"|"none",
            "summary": "short summary",
            "key_dates": [{"label": "Due date", "date": "2026-05-01"}],
            "course_hint": "CS-101" or null,
            "department_hint": "CS" or null,
            "title_hint": "Homework 3" or null,
        }
    """
    settings = get_settings()
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key

    llm = ChatOpenAI(model=settings.openai_model, temperature=0)

    prompt = f"""You are a document classifier for a university portal.
The uploader's role is: {uploader_role}.
The excerpt below is ONLY THE BEGINNING of the PDF (header / title area). Infer metadata from that.
Analyze text extracted from a PDF named "{filename}" and return ONLY valid JSON with these keys:

- "document_type": one of "assignment", "submission", "transcript", "fee", "hostel", "library", "complaint", "notice", "syllabus", "report", "other"
    - Use "assignment" when a TEACHER is publishing/creating a new assignment for students.
    - Use "submission" when a STUDENT is submitting/turning in their completed work for an assignment.
- "notify_target": decide who should be emailed about this document. Pick ONE:
    "students"       — if it is an assignment, syllabus, or class material that students need to know about
    "course_teacher" — if it is a student submission that should go to the course teacher
    "exam_staff"     — if it is a transcript request, exam schedule, admit card, or result related
    "finance_staff"  — if it is about fees, challans, payments, refunds, or financial matters
    "hostel_staff"   — if it is about hostel, accommodation, room allotment
    "library_staff"  — if it is about library books, fines, returns
    "admin_staff"    — if it is a complaint, grievance, general request, or administrative matter
    "department"     — if it is a departmental notice or circular
    "none"           — if you cannot determine who should be notified
- "summary": a 1-2 sentence summary of the document
- "key_dates": a list of objects like {{"label": "Due date", "date": "2026-05-01"}}. Empty list if none found.
- "course_hint": the course code if explicitly mentioned (e.g. "CS301"), or null
- "course_subject_hint": the subject or course NAME that this document is about (e.g. "Natural Language Processing", "Database Systems", "Machine Learning"), or null. Extract this from context even if no course code is given.
- "department_hint": the department code if mentioned (e.g. "CS", "AI", "BBA"), or null
- "title_hint": the document title if found, or null
- "total_marks_hint": integer total marks/points if the document states them (e.g. 20, 100), else null

--- DOCUMENT TEXT ---
{text[:4000]}
--- END TEXT ---

Respond with ONLY the JSON object, no markdown fences, no explanation."""

    try:
        result = llm.invoke(prompt)
        content = result.content.strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content.strip())
    except Exception as e:
        log.error("Document classification failed: %s", e)
        return {
            "document_type": "other",
            "notify_target": "none",
            "summary": "Could not classify the document.",
            "key_dates": [],
            "course_hint": None,
            "course_subject_hint": None,
            "department_hint": None,
            "title_hint": None,
            "total_marks_hint": None,
        }


def _notify_students_whatsapp_new_assignment(
    course_id_str: str,
    course_code: str,
    title: str,
    summary: str,
    due_iso: str,
    assignment_id_str: str,
    download_base_url: str | None = None,
) -> int:
    """Notify enrolled students (with phone on file) about a new assignment + signed PDF link."""
    from services import assignment_upload_service as asvc
    from services.whatsapp_service import is_configured, send_text_message, pick_whatsapp_phone

    if not is_configured():
        return 0
    try:
        cid = ObjectId(course_id_str)
    except Exception:
        return 0

    db = _db()
    enrollments = list(
        db["enrollments"].find({"course_id": cid, "status": "active"}, {"student_id": 1})
    )
    sids = [e["student_id"] for e in enrollments]
    if not sids:
        return 0

    students = list(db["students"].find({"_id": {"$in": sids}}))
    short_sum = (summary or "").strip()[:400]
    sent = 0
    for st in students:
        phone = pick_whatsapp_phone(st)
        if not phone:
            continue
        try:
            dl_tok = asvc.mint_assignment_download_token(
                str(st["_id"]), "student", assignment_id_str
            )
            dl_url = asvc.build_signed_assignment_url(dl_tok, download_base_url)
        except Exception as exc:
            log.warning("Could not mint download link for student %s: %s", st.get("_id"), exc)
            dl_url = ""
        body = (
            f"📚 New assignment\n*{title}*\n"
            f"Course: {course_code}\n"
            f"Due: {due_iso}\n\n"
            f"{short_sum}\n\n"
        )
        if dl_url:
            body += f"Download full PDF:\n{dl_url}\n\n"
        body += "Open the IBA portal or reply here for help."
        if send_text_message(phone, body).get("success"):
            sent += 1
    log.info(
        "WhatsApp: new assignment notices for %s → %d students",
        course_code,
        sent,
    )
    return sent


def _notify_teacher_whatsapp_submission(
    teacher_id_str: str | None,
    student_name: str,
    course_code: str,
    assignment_title: str,
    submission_pdf_url: str | None = None,
) -> bool:
    from services.whatsapp_service import is_configured, send_text_message, pick_whatsapp_phone

    if not is_configured() or not teacher_id_str:
        return False
    try:
        tid = ObjectId(teacher_id_str)
    except Exception:
        return False

    db = _db()
    teacher = db["teachers"].find_one({"_id": tid})
    if not teacher:
        return False
    phone = pick_whatsapp_phone(teacher)
    if not phone:
        return False

    body = (
        f"📥 Assignment submitted\n"
        f"Student: {student_name}\n"
        f"Course: {course_code}\n"
        f"Task: {assignment_title}\n\n"
    )
    if submission_pdf_url:
        body += f"📎 Submitted PDF (signed link):\n{submission_pdf_url}\n\n"
    body += "Review on the IBA portal."
    return bool(send_text_message(phone, body).get("success"))


# ═══════════════════════════════════════════════════════════════════════
# 2. RECIPIENT RESOLVERS — queries MongoDB to find the right people
# ═══════════════════════════════════════════════════════════════════════

def _get_enrolled_students_for_teacher(teacher_id: str) -> list[dict[str, str]]:
    """Students enrolled in courses taught by this teacher."""
    db = _db()
    try:
        teacher = db["teachers"].find_one({"_id": ObjectId(teacher_id)})
    except Exception:
        return []
    if not teacher:
        return []

    course_codes = teacher.get("assigned_course_codes") or []
    dept = teacher.get("department")
    if not course_codes:
        return []

    courses = list(db["courses"].find(
        {"course_code": {"$in": course_codes}, "department": dept, "is_active": True}
    ))
    course_ids = [c["_id"] for c in courses]
    if not course_ids:
        return []

    enrollments = list(db["enrollments"].find(
        {"course_id": {"$in": course_ids}, "status": "active"},
        {"student_id": 1},
    ))
    student_ids = list({e["student_id"] for e in enrollments})
    if not student_ids:
        return []

    students = db["students"].find(
        {"_id": {"$in": student_ids}},
        {"email": 1, "full_name": 1, "roll_number": 1},
    )
    return [
        {"email": s.get("email", ""), "full_name": s.get("full_name", ""), "role": "student"}
        for s in students if s.get("email")
    ]


def _get_staff_by_role(role: str) -> list[dict[str, str]]:
    """Get staff members by their role (exam_staff, finance_staff, etc.)."""
    db = _db()
    staff = db["staff"].find(
        {"role": role, "status": "active"},
        {"email": 1, "full_name": 1, "role": 1},
    )
    return [
        {"email": s.get("email", ""), "full_name": s.get("full_name", ""), "role": role}
        for s in staff if s.get("email")
    ]


def _get_department_teachers(department: str) -> list[dict[str, str]]:
    """Get all teachers in a specific department."""
    db = _db()
    teachers = db["teachers"].find(
        {"department": department, "status": "active"},
        {"email": 1, "full_name": 1},
    )
    return [
        {"email": t.get("email", ""), "full_name": t.get("full_name", ""), "role": "teacher"}
        for t in teachers if t.get("email")
    ]


def _resolve_recipients(
    notify_target: str,
    session_user_role: str,
    session_user_id: str,
    department_hint: str | None,
) -> list[dict[str, str]]:
    """
    Based on classify_document's notify_target, fetch the right
    recipients from MongoDB.
    """
    if notify_target == "students" and session_user_role == "teacher":
        return _get_enrolled_students_for_teacher(session_user_id)

    if notify_target == "course_teacher" and session_user_role == "student":
        # The submission handler already resolved the teacher — check result context
        # We'll handle this in handle_document_upload by injecting recipients directly
        return []

    if notify_target == "exam_staff":
        return _get_staff_by_role("exam_staff")

    if notify_target == "finance_staff":
        return _get_staff_by_role("finance_staff")

    if notify_target == "hostel_staff":
        return _get_staff_by_role("hostel_staff")

    if notify_target == "library_staff":
        return _get_staff_by_role("library_staff")

    if notify_target == "admin_staff":
        return _get_staff_by_role("admin_staff")

    if notify_target == "department":
        dept = department_hint
        if not dept and session_user_role in ("teacher", "student"):
            # try to get from uploader's profile
            db = _db()
            col = "teachers" if session_user_role == "teacher" else "students"
            try:
                doc = db[col].find_one({"_id": ObjectId(session_user_id)}, {"department": 1})
                dept = doc.get("department") if doc else None
            except Exception:
                pass
        if dept:
            return _get_department_teachers(dept)

    return []


# ═══════════════════════════════════════════════════════════════════════
# 3. MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

# Human-readable labels for the chat response
_TARGET_LABELS = {
    "students": "enrolled students",
    "course_teacher": "Course Teacher",
    "exam_staff": "Examination Office",
    "finance_staff": "Finance Department",
    "hostel_staff": "Hostel Office",
    "library_staff": "Library Staff",
    "admin_staff": "Administration",
    "department": "Department Faculty",
}


def handle_document_upload(
    text: str,
    filename: str,
    session_user_role: str,
    session_user_id: str,
    session_user_name: str,
    source_tag: str = "chat_upload",
    pdf_bytes: bytes | None = None,
    download_base_url: str | None = None,
) -> dict[str, Any]:
    """
    Main entry point:
      1. Classify using only the header excerpt of the PDF text (metadata extraction)
      2. If assignment + teacher → save to DB, optionally persist PDF on disk
      3. Mint signed download URL for the uploader (and per-student links on WhatsApp)
      4. Send email when SMTP is configured
    """
    header = _assignment_header_text(text)
    classification = classify_document(header, filename, uploader_role=session_user_role)
    doc_type = classification.get("document_type", "other")
    notify_target = classification.get("notify_target", "none")
    summary = classification.get("summary", "") or ""
    key_dates = classification.get("key_dates", [])
    department_hint = classification.get("department_hint")
    course_hint = classification.get("course_hint")
    course_subject_hint = classification.get("course_subject_hint")
    total_marks = _normalize_marks_hint(classification.get("total_marks_hint"))

    fn_base = (filename or "document.pdf").strip().rsplit("/", 1)[-1]
    title_raw = (classification.get("title_hint") or "").strip()
    weak_title = (
        not title_raw
        or title_raw.lower() == fn_base.lower()
        or title_raw.lower() in ("unknown", "untitled", "document", "assignment")
    )
    if weak_title:
        title = infer_assignment_title(header, summary, course_hint or "", fn_base)
    else:
        title = title_raw

    result: dict[str, Any] = {
        "classification": classification,
        "email_sent": False,
        "email_details": None,
        "email_configured": smtp_is_configured(),
        "notify_target_label": _TARGET_LABELS.get(notify_target, notify_target),
        "assignment_saved": False,
        "submission_recorded": False,
        "whatsapp_students_notified": 0,
        "whatsapp_teacher_notified": False,
        "download_signed_url": None,
    }

    # ── Teacher uploading an assignment → save to DB ──
    if doc_type == "assignment" and session_user_role == "teacher":
        save_result = _save_assignment_to_db(
            teacher_id=session_user_id,
            title=title,
            summary=summary,
            key_dates=key_dates,
            course_hint=course_hint,
            course_subject_hint=course_subject_hint,
            total_marks=total_marks,
            source=source_tag,
            pdf_bytes=pdf_bytes,
            original_filename=fn_base,
        )
        result["assignment_saved"] = save_result.get("saved", False)
        result["assignment_save_details"] = save_result
        if save_result.get("saved") and save_result.get("assignment_id"):
            from services import assignment_upload_service as asvc

            try:
                tok = asvc.mint_assignment_download_token(
                    session_user_id, session_user_role, save_result["assignment_id"]
                )
                result["download_signed_url"] = asvc.build_signed_assignment_url(
                    tok, download_base_url
                )
                save_result["download_signed_url"] = result["download_signed_url"]
            except Exception as exc:
                log.warning("Could not mint teacher download URL: %s", exc)

        if save_result.get("saved") and save_result.get("course_id"):
            result["whatsapp_students_notified"] = _notify_students_whatsapp_new_assignment(
                save_result["course_id"],
                save_result.get("course_code", ""),
                title,
                summary,
                save_result.get("due_date", ""),
                save_result.get("assignment_id", ""),
                download_base_url,
            )

    # ── Student submitting assignment → update submission + notify teacher ──
    if doc_type == "submission" and session_user_role == "student":
        sub_result = _handle_student_submission(
            student_id=session_user_id,
            student_name=session_user_name,
            course_hint=course_hint,
            course_subject_hint=course_subject_hint,
            title=title,
            pdf_bytes=pdf_bytes,
            original_filename=fn_base,
            download_base_url=download_base_url,
        )
        result["submission_recorded"] = sub_result.get("recorded", False)
        result["submission_details"] = sub_result
        if sub_result.get("student_submission_signed_url"):
            result["submission_download_signed_url"] = sub_result["student_submission_signed_url"]
        if sub_result.get("teacher_email"):
            notify_target = "course_teacher"
            result["notify_target_label"] = _TARGET_LABELS.get("course_teacher", "Course Teacher")
        if sub_result.get("submission_updated") and sub_result.get("teacher_id"):
            result["whatsapp_teacher_notified"] = _notify_teacher_whatsapp_submission(
                sub_result.get("teacher_id"),
                session_user_name,
                sub_result.get("course_code", ""),
                sub_result.get("assignment_title", title),
                submission_pdf_url=sub_result.get("teacher_submission_signed_url"),
            )

    # Skip email if SMTP isn't configured
    if not smtp_is_configured():
        log.warning("SMTP not configured — skipping email notification for uploaded document.")
        return result

    # Skip if no target was identified
    if notify_target == "none":
        log.info("No email target identified for document '%s' (type=%s)", filename, doc_type)
        return result

    # Resolve recipients
    recipients = _resolve_recipients(
        notify_target=notify_target,
        session_user_role=session_user_role,
        session_user_id=session_user_id,
        department_hint=department_hint,
    )

    # For student submissions, inject teacher directly from submission result
    if notify_target == "course_teacher" and not recipients:
        sub_details = result.get("submission_details", {})
        if sub_details.get("teacher_email"):
            recipients = [{
                "email": sub_details["teacher_email"],
                "full_name": sub_details.get("teacher_name", ""),
                "role": "teacher",
            }]

    if not recipients:
        log.info("No recipients found for notify_target=%s", notify_target)
        return result

    # Build email
    dates_text = ""
    if key_dates:
        dates_text = " | ".join(
            f"{d.get('label', 'Date')}: {d.get('date', 'N/A')}" for d in key_dates
        )

    target_label = _TARGET_LABELS.get(notify_target, notify_target)

    body_lines = [
        f"Dear {target_label},",
        f"",
        f"<b>{session_user_name}</b> ({session_user_role}) has uploaded a new document: <b>{title}</b>.",
        f"",
        f"<b>Document Type:</b> {doc_type.replace('_', ' ').title()}",
        f"<b>Summary:</b> {summary}",
    ]
    if dates_text:
        body_lines.append(f"<b>Important dates:</b> {dates_text}")
    sub_deets = result.get("submission_details") or {}
    if sub_deets.get("teacher_submission_signed_url"):
        body_lines.append(
            f"<b>Submitted work (PDF):</b> {sub_deets['teacher_submission_signed_url']}"
        )
    body_lines += [
        f"",
        f"Please log in to the IBA Sukkur Portal to review and take necessary action.",
    ]

    subject = f"[IBA Portal] New {doc_type.replace('_', ' ').title()}: {title}"

    email_result = send_bulk_email(
        recipients=recipients,
        subject=subject,
        body_lines=body_lines,
    )

    result["email_sent"] = email_result.get("sent", 0) > 0
    result["email_details"] = email_result
    log.info(
        "Email notification: target=%s, sent=%d, failed=%d (uploader=%s)",
        notify_target, email_result["sent"], email_result["failed"], session_user_name,
    )

    return result


# ═══════════════════════════════════════════════════════════════════════
# 4. SAVE ASSIGNMENT TO DB
# ═══════════════════════════════════════════════════════════════════════

def _save_assignment_to_db(
    teacher_id: str,
    title: str,
    summary: str,
    key_dates: list[dict],
    course_hint: str | None,
    course_subject_hint: str | None = None,
    total_marks: int = 100,
    source: str = "chat_upload",
    pdf_bytes: bytes | None = None,
    original_filename: str | None = None,
) -> dict[str, Any]:
    """
    When the LLM says it's an assignment and a teacher uploaded it,
    save it to the assignments collection + create pending submission
    rows for enrolled students so the chatbot can find it.

    Course matching priority:
      1. Exact course_code match (e.g. "CS301")
      2. NLP subject name match against the teacher's assigned course names
      3. Fallback to teacher's first assigned course
    """
    from datetime import datetime, timezone, timedelta

    db = _db()
    try:
        teacher = db["teachers"].find_one({"_id": ObjectId(teacher_id)})
    except Exception:
        return {"saved": False, "reason": "Invalid teacher ID"}
    if not teacher:
        return {"saved": False, "reason": "Teacher not found"}

    # Figure out which course to assign it to
    assigned_codes = teacher.get("assigned_course_codes") or []
    dept = teacher.get("department")
    if not assigned_codes:
        return {"saved": False, "reason": "Teacher has no assigned courses"}

    # Load actual course docs for this teacher
    teacher_courses = list(db["courses"].find(
        {"course_code": {"$in": assigned_codes}, "department": dept, "is_active": True}
    ))

    course = None

    # Strategy 1: Exact course_code match
    if course_hint:
        normalized = course_hint.replace("-", "").replace(" ", "").upper()
        for c in teacher_courses:
            if c["course_code"].replace("-", "").replace(" ", "").upper() == normalized:
                course = c
                break

    # Strategy 2: Match subject name from the document against course names
    if not course and course_subject_hint:
        subject_lower = course_subject_hint.lower()
        subject_words = set(subject_lower.split())
        # Remove filler words
        filler = {"and", "the", "of", "in", "to", "for", "a", "an", "with"}
        subject_words -= filler

        best_match = None
        best_score = 0
        for c in teacher_courses:
            cname_lower = c["course_name"].lower()
            cname_words = set(cname_lower.split()) - filler

            # Check if subject name is a substring of course name or vice versa
            if subject_lower in cname_lower or cname_lower in subject_lower:
                course = c
                break

            # Word overlap scoring
            overlap = len(subject_words & cname_words)
            if overlap > best_score:
                best_score = overlap
                best_match = c

        if not course and best_match and best_score >= 1:
            course = best_match

    # Strategy 3: Fallback to first assigned course
    if not course and teacher_courses:
        course = teacher_courses[0]

    if not course:
        return {"saved": False, "reason": "No matching course found"}

    course_code = course["course_code"]

    now = datetime.now(timezone.utc)

    # Parse due date from key_dates
    due_date = None
    opens_at = None
    for kd in key_dates:
        label = (kd.get("label") or "").lower()
        date_str = kd.get("date")
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if any(w in label for w in ["due", "deadline", "submit", "close"]):
            due_date = dt
        elif any(w in label for w in ["open", "start", "release", "available"]):
            opens_at = dt

    if not due_date:
        due_date = now + timedelta(days=14)
    if not opens_at:
        opens_at = now

    marks = int(total_marks) if total_marks else 100
    if marks < 1:
        marks = 100

    from services import assignment_upload_service as asvc

    aid = ObjectId()
    att_orig = None
    att_stored = None
    att_mime = None
    if pdf_bytes and len(pdf_bytes) > 0 and asvc.verify_pdf_magic(pdf_bytes[:4096]):
        stored_rel = f"{aid}.pdf"
        dest = asvc.get_upload_dir() / stored_rel
        dest.write_bytes(pdf_bytes)
        att_orig = asvc._safe_pdf_name(original_filename or "assignment.pdf")
        att_stored = stored_rel
        att_mime = "application/pdf"

    doc = asvc.build_assignment_document(
        aid=aid,
        course=course,
        course_code=course_code,
        title=title,
        description=summary or "See uploaded document for details.",
        teacher_oid=ObjectId(teacher_id),
        total_marks=marks,
        due_date=due_date,
        opens_at=opens_at,
        source=source,
        university=course.get("university", "IBA Sukkur"),
        now=now,
        attachment_original_name=att_orig,
        attachment_stored_name=att_stored,
        attachment_mime=att_mime,
    )
    db["assignments"].insert_one(doc)

    students_count = asvc.insert_pending_submissions_for_assignment(
        db,
        assignment_id=aid,
        course_id=course["_id"],
        course_code=course_code,
        teacher_oid=ObjectId(teacher_id),
        out_of=marks,
        university=doc["university"],
    )

    log.info(
        "Assignment saved: '%s' for %s (%d students notified in DB)",
        title, course_code, students_count,
    )
    return {
        "saved": True,
        "assignment_id": str(aid),
        "course_id": str(course["_id"]),
        "course_code": course_code,
        "course_name": course.get("course_name", course_code),
        "due_date": due_date.isoformat(),
        "opens_at": doc["opens_at"].isoformat(),
        "students_count": students_count,
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. HANDLE STUDENT SUBMISSION
# ═══════════════════════════════════════════════════════════════════════

def _submission_title_match_score(assignment_title: str, hint: str) -> int:
    """Word overlap between assignment title and NLP hint (higher = better match)."""
    def _words(s: str) -> set[str]:
        w = set(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())
        filler = {
            "the", "a", "an", "for", "and", "or", "of", "in", "to", "assignment",
            "homework", "task", "project", "lab",
        }
        return w - filler

    return len(_words(assignment_title) & _words(hint))


def _handle_student_submission(
    student_id: str,
    student_name: str,
    course_hint: str | None,
    course_subject_hint: str | None,
    title: str,
    pdf_bytes: bytes | None = None,
    original_filename: str | None = None,
    download_base_url: str | None = None,
) -> dict[str, Any]:
    """
    When the LLM classifies a student's upload as a submission (not teacher assignment creation):
      1. Resolve course from enrollments + hints
      2. Pick best matching pending/overdue submission row (title match)
      3. Mark submitted, optionally persist PDF + signed URLs for student & teacher
    """
    from datetime import datetime, timezone

    from services import assignment_upload_service as asvc

    db = _db()
    now = datetime.now(timezone.utc)

    try:
        student = db["students"].find_one({"_id": ObjectId(student_id)})
    except Exception:
        return {"recorded": False, "reason": "Invalid student ID"}
    if not student:
        return {"recorded": False, "reason": "Student not found"}

    dept = student.get("department")

    enrollments = list(db["enrollments"].find(
        {"student_id": ObjectId(student_id), "status": "active"}
    ))
    if not enrollments:
        return {"recorded": False, "reason": "Student has no active enrollments"}

    enrolled_codes = [e["course_code"] for e in enrollments]
    enrolled_courses = list(db["courses"].find(
        {"course_code": {"$in": enrolled_codes}, "is_active": True}
    ))

    course = None

    if course_hint:
        normalized = course_hint.replace("-", "").replace(" ", "").upper()
        for c in enrolled_courses:
            if c["course_code"].replace("-", "").replace(" ", "").upper() == normalized:
                course = c
                break

    if not course and course_subject_hint:
        subject_lower = course_subject_hint.lower()
        subject_words = set(subject_lower.split())
        filler = {"and", "the", "of", "in", "to", "for", "a", "an", "with"}
        subject_words -= filler

        best_match = None
        best_score = 0
        for c in enrolled_courses:
            cname_lower = c["course_name"].lower()
            cname_words = set(cname_lower.split()) - filler

            if subject_lower in cname_lower or cname_lower in subject_lower:
                course = c
                break

            overlap = len(subject_words & cname_words)
            if overlap > best_score:
                best_score = overlap
                best_match = c

        if not course and best_match and best_score >= 1:
            course = best_match

    if not course and title:
        title_lower = title.lower()
        for c in enrolled_courses:
            if c["course_name"].lower() in title_lower:
                course = c
                break

    if not course:
        return {"recorded": False, "reason": "Could not determine which course this submission belongs to"}

    course_code = course["course_code"]

    candidates = list(db["assignment_submissions"].find({
        "student_id": ObjectId(student_id),
        "course_code": course_code,
        "status": {"$in": ["pending", "overdue"]},
    }))

    pending_sub = None
    assignment_title = title

    if candidates:
        scored: list[tuple[int, Any]] = []
        for sub in candidates:
            asn = db["assignments"].find_one({"_id": sub["assignment_id"]})
            atitle = (asn or {}).get("title") or ""
            sc = _submission_title_match_score(atitle, title)
            scored.append((sc, sub))
        scored.sort(
            key=lambda x: (
                -x[0],
                0 if (x[1].get("status") or "") == "pending" else 1,
            )
        )
        pending_sub = scored[0][1]
        asn0 = db["assignments"].find_one({"_id": pending_sub["assignment_id"]})
        if asn0:
            assignment_title = asn0.get("title", title)

    student_sub_url: str | None = None
    teacher_sub_url: str | None = None

    if pending_sub:
        update_fields: dict[str, Any] = {
            "status": "submitted",
            "submitted_at": now,
        }

        if (
            pdf_bytes
            and len(pdf_bytes) > 0
            and asvc.verify_pdf_magic(pdf_bytes[:4096])
        ):
            sub_oid = pending_sub["_id"]
            stored_rel = f"{sub_oid}.pdf"
            dest = asvc.get_submission_upload_dir() / stored_rel
            dest.write_bytes(pdf_bytes)
            update_fields["submission_attachment_stored_name"] = stored_rel
            update_fields["submission_attachment_original_name"] = asvc._safe_pdf_name(
                original_filename or "submission.pdf"
            )
            update_fields["submission_attachment_mime"] = "application/pdf"

        db["assignment_submissions"].update_one(
            {"_id": pending_sub["_id"]},
            {"$set": update_fields},
        )

        sub_row_id = str(pending_sub["_id"])
        if update_fields.get("submission_attachment_stored_name"):
            try:
                st_tok = asvc.mint_submission_download_token(
                    student_id, "student", sub_row_id
                )
                student_sub_url = asvc.build_signed_submission_url(
                    st_tok, download_base_url
                )
                tid_for_tok = str(pending_sub.get("teacher_id") or "")
                if tid_for_tok:
                    tt_tok = asvc.mint_submission_download_token(
                        tid_for_tok, "teacher", sub_row_id
                    )
                    teacher_sub_url = asvc.build_signed_submission_url(
                        tt_tok, download_base_url
                    )
            except Exception as exc:
                log.warning("Could not mint submission download URLs: %s", exc)
    else:
        log.info(
            "No pending/overdue submission for student %s in %s — no row updated",
            student_id,
            course_code,
        )

    # Prefer instructor on the submission row (same as assignment creator)
    teacher = None
    if pending_sub and pending_sub.get("teacher_id"):
        raw_tid = pending_sub["teacher_id"]
        try:
            teacher = db["teachers"].find_one({"_id": ObjectId(str(raw_tid))})
        except Exception:
            teacher = db["teachers"].find_one({"_id": raw_tid})
    if not teacher:
        teacher = db["teachers"].find_one({
            "assigned_course_codes": course_code,
            "department": dept,
        })

    teacher_email = None
    teacher_name = None
    teacher_id_str: str | None = None
    if teacher:
        teacher_email = teacher.get("email")
        teacher_name = teacher.get("full_name")
        teacher_id_str = str(teacher["_id"])

    log.info(
        "Student submission: %s → %s (%s) updated=%s file=%s",
        student_name,
        course_code,
        assignment_title,
        pending_sub is not None,
        bool(pdf_bytes and pending_sub),
    )

    return {
        "recorded": True,
        "course_code": course_code,
        "course_name": course.get("course_name", course_code),
        "assignment_title": assignment_title,
        "teacher_name": teacher_name,
        "teacher_email": teacher_email,
        "teacher_id": teacher_id_str,
        "submission_updated": pending_sub is not None,
        "submission_row_id": str(pending_sub["_id"]) if pending_sub else None,
        "student_submission_signed_url": student_sub_url,
        "teacher_submission_signed_url": teacher_sub_url,
    }
