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
from typing import Any

from langchain_openai import ChatOpenAI
from pymongo import MongoClient
from bson import ObjectId

from config import get_settings
from services.email_service import send_bulk_email, is_configured as smtp_is_configured

log = logging.getLogger(__name__)


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
Analyze the following text extracted from a PDF named "{filename}" and return ONLY valid JSON with these keys:

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
        }


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
) -> dict[str, Any]:
    """
    Main entry point:
      1. Classify the document via NLP
      2. If assignment + teacher → save to DB so students can query it
      3. Check if SMTP is configured
      4. Resolve the right recipients from the DB based on document type
      5. Send email notifications
      6. Return result with classification + email status
    """
    classification = classify_document(text, filename, uploader_role=session_user_role)
    doc_type = classification.get("document_type", "other")
    notify_target = classification.get("notify_target", "none")
    summary = classification.get("summary", "")
    title = classification.get("title_hint") or filename
    key_dates = classification.get("key_dates", [])
    department_hint = classification.get("department_hint")
    course_hint = classification.get("course_hint")
    course_subject_hint = classification.get("course_subject_hint")

    result: dict[str, Any] = {
        "classification": classification,
        "email_sent": False,
        "email_details": None,
        "email_configured": smtp_is_configured(),
        "notify_target_label": _TARGET_LABELS.get(notify_target, notify_target),
        "assignment_saved": False,
        "submission_recorded": False,
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
        )
        result["assignment_saved"] = save_result.get("saved", False)
        result["assignment_save_details"] = save_result

    # ── Student submitting assignment → update submission + notify teacher ──
    if doc_type == "submission" and session_user_role == "student":
        sub_result = _handle_student_submission(
            student_id=session_user_id,
            student_name=session_user_name,
            course_hint=course_hint,
            course_subject_hint=course_subject_hint,
            title=title,
        )
        result["submission_recorded"] = sub_result.get("recorded", False)
        result["submission_details"] = sub_result
        # Override notify_target so email goes to the teacher
        if sub_result.get("teacher_email"):
            notify_target = "course_teacher"
            result["notify_target_label"] = _TARGET_LABELS.get("course_teacher", "Course Teacher")

    # Skip if SMTP isn't configured
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

    # Insert assignment
    aid = ObjectId()
    doc = {
        "_id": aid,
        "course_id": course["_id"],
        "course_code": course_code,
        "title": title,
        "description": summary or "See uploaded document for details.",
        "created_by_teacher": ObjectId(teacher_id),
        "total_marks": 100,
        "due_date": due_date,
        "opens_at": opens_at,
        "is_past": due_date < now,
        "is_active": True,
        "semester": course.get("semester"),
        "created_at": now,
        "university": course.get("university", "IBA Sukkur"),
        "source": "chat_upload",
    }
    db["assignments"].insert_one(doc)

    # Create pending submissions for enrolled students
    enrollments = list(db["enrollments"].find(
        {"course_id": course["_id"], "status": "active"},
        {"student_id": 1},
    ))
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
        subs.append({
            "assignment_id": aid,
            "course_id": course["_id"],
            "course_code": course_code,
            "student_id": sid,
            "student_name": st.get("full_name", ""),
            "student_roll": st.get("roll_number", ""),
            "teacher_id": ObjectId(teacher_id),
            "status": "pending",
            "submitted_at": None,
            "marks_obtained": 0,
            "out_of": 100,
            "feedback": None,
            "graded": False,
            "graded_at": None,
            "is_flagged": False,
            "flag_reason": None,
            "university": course.get("university", "IBA Sukkur"),
        })
    if subs:
        db["assignment_submissions"].insert_many(subs)

    log.info(
        "Assignment saved: '%s' for %s (%d students notified in DB)",
        title, course_code, len(subs),
    )
    return {
        "saved": True,
        "assignment_id": str(aid),
        "course_code": course_code,
        "course_name": course.get("course_name", course_code),
        "due_date": due_date.isoformat(),
        "students_count": len(subs),
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. HANDLE STUDENT SUBMISSION
# ═══════════════════════════════════════════════════════════════════════

def _handle_student_submission(
    student_id: str,
    student_name: str,
    course_hint: str | None,
    course_subject_hint: str | None,
    title: str,
) -> dict[str, Any]:
    """
    When the LLM classifies a student's upload as a submission:
      1. Find the matching course from the student's enrollments
      2. Find a pending assignment for that course
      3. Update the submission record to 'submitted'
      4. Return teacher info so we can send them an email
    """
    from datetime import datetime, timezone

    db = _db()
    now = datetime.now(timezone.utc)

    try:
        student = db["students"].find_one({"_id": ObjectId(student_id)})
    except Exception:
        return {"recorded": False, "reason": "Invalid student ID"}
    if not student:
        return {"recorded": False, "reason": "Student not found"}

    dept = student.get("department")
    roll = student.get("roll_number", "")

    # Get student's active enrollments
    enrollments = list(db["enrollments"].find(
        {"student_id": ObjectId(student_id), "status": "active"}
    ))
    if not enrollments:
        return {"recorded": False, "reason": "Student has no active enrollments"}

    enrolled_codes = [e["course_code"] for e in enrollments]
    enrolled_courses = list(db["courses"].find(
        {"course_code": {"$in": enrolled_codes}, "is_active": True}
    ))

    # Match course using same 3-strategy approach
    course = None

    # Strategy 1: Exact course code
    if course_hint:
        normalized = course_hint.replace("-", "").replace(" ", "").upper()
        for c in enrolled_courses:
            if c["course_code"].replace("-", "").replace(" ", "").upper() == normalized:
                course = c
                break

    # Strategy 2: Subject name matching
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

    # Strategy 3: Try matching from assignment title
    if not course and title:
        title_lower = title.lower()
        for c in enrolled_courses:
            if c["course_name"].lower() in title_lower:
                course = c
                break

    if not course:
        return {"recorded": False, "reason": "Could not determine which course this submission belongs to"}

    course_code = course["course_code"]

    # Find a pending assignment for this student + course
    pending_sub = db["assignment_submissions"].find_one({
        "student_id": ObjectId(student_id),
        "course_code": course_code,
        "status": "pending",
    })

    assignment_title = title
    if pending_sub:
        # Update submission status
        db["assignment_submissions"].update_one(
            {"_id": pending_sub["_id"]},
            {"$set": {
                "status": "submitted",
                "submitted_at": now,
            }}
        )
        # Get assignment title
        assignment = db["assignments"].find_one({"_id": pending_sub["assignment_id"]})
        if assignment:
            assignment_title = assignment.get("title", title)
    else:
        log.info("No pending submission found for student %s in %s, skipping DB update", student_id, course_code)

    # Find the teacher for this course
    teacher = db["teachers"].find_one({
        "assigned_course_codes": course_code,
        "department": dept,
    })

    teacher_email = None
    teacher_name = None
    if teacher:
        teacher_email = teacher.get("email")
        teacher_name = teacher.get("full_name")

    log.info(
        "Student submission: %s submitted for %s (%s) → teacher: %s",
        student_name, course_code, assignment_title, teacher_name or "not found",
    )

    return {
        "recorded": True,
        "course_code": course_code,
        "course_name": course.get("course_name", course_code),
        "assignment_title": assignment_title,
        "teacher_name": teacher_name,
        "teacher_email": teacher_email,
        "submission_updated": pending_sub is not None,
    }
