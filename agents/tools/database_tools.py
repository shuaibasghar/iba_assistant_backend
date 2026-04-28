"""
Database Query Tools for CrewAI Agents
These tools allow agents to query the MongoDB database.
"""

from crewai.tools import BaseTool
from typing import Any, Type
from pydantic import BaseModel, Field
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone
from config import get_settings
from services.assignment_upload_service import (
    assignment_has_downloadable_pdf,
    build_signed_assignment_url,
    mint_assignment_download_token,
    teacher_submissions_overview,
)
from services.portal_update_service import portal_record_update
from services.superadmin_directory_service import run_superadmin_directory_op
from services.portal_export_service import run_export_for_chat
from services.portal_read_query_service import run_portal_read_query


def get_db():
    """Get MongoDB database connection."""
    settings = get_settings()
    client = MongoClient(settings.mongodb_url)
    return client[settings.mongodb_database]


# ═══════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════

def find_student(db, student_id: str):
    """
    Find a student by ObjectId or roll_number.
    Returns the student document or None.
    """
    # Try as ObjectId first (24-char hex string)
    if len(student_id) == 24:
        try:
            student = db["students"].find_one({"_id": ObjectId(student_id)})
            if student:
                return student
        except:
            pass
    
    # Try as roll_number
    student = db["students"].find_one({"roll_number": student_id})
    if student:
        return student
    
    # Try as email
    student = db["students"].find_one({"email": student_id})
    return student


def find_teacher(db, teacher_id: str):
    """
    Find a teacher by ObjectId, employee_id, or email.
    """
    if len(teacher_id) == 24:
        try:
            t = db["teachers"].find_one({"_id": ObjectId(teacher_id)})
            if t:
                return t
        except Exception:
            pass
    t = db["teachers"].find_one({"employee_id": teacher_id})
    if t:
        return t
    return db["teachers"].find_one({"email": teacher_id})


def _assignment_upload_recency_ts(a: dict) -> float:
    """When the assignment was published (created_at), else BSON ObjectId time."""
    ca = a.get("created_at")
    if ca is not None:
        if getattr(ca, "tzinfo", None) is None:
            ca = ca.replace(tzinfo=timezone.utc)
        return float(ca.timestamp())
    oid = a.get("_id")
    if isinstance(oid, ObjectId):
        return float(oid.generation_time.replace(tzinfo=timezone.utc).timestamp())
    return 0.0


def _strip_internal_assignment_fields(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_recency_ts"}


def find_admin(db, admin_id: str):
    """Find an admin document by ObjectId, employee_id, or email."""
    if len(admin_id) == 24:
        try:
            a = db["admins"].find_one({"_id": ObjectId(admin_id)})
            if a:
                return a
        except Exception:
            pass
    a = db["admins"].find_one({"employee_id": admin_id})
    if a:
        return a
    return db["admins"].find_one({"email": admin_id})


def find_superadmin(db, user_id: str):
    """Find a superadmin document by ObjectId or email."""
    if len(user_id) == 24:
        try:
            s = db["superadmins"].find_one({"_id": ObjectId(user_id)})
            if s:
                return s
        except Exception:
            pass
    return db["superadmins"].find_one({"email": user_id})


# ═══════════════════════════════════════════════════════════════════
# Tool Input Schemas
# ═══════════════════════════════════════════════════════════════════

class StudentIdInput(BaseModel):
    """Input schema for tools that need student_id."""
    student_id: str = Field(..., description="Student identifier - can be MongoDB ObjectId, roll_number (e.g., CS-2023-001), or email")


class StudentSemesterInput(BaseModel):
    """Input schema for tools that need student_id and optional semester."""
    student_id: str = Field(..., description="Student identifier - can be MongoDB ObjectId, roll_number (e.g., CS-2023-001), or email")
    semester: int | None = Field(None, description="Specific semester to query (optional)")


class TeacherSubmissionsInput(BaseModel):
    """Teacher portal user id plus optional assignment to filter the roster."""
    teacher_id: str = Field(
        ...,
        description="MongoDB teachers._id string from session (same as query_teacher_teaching)",
    )
    assignment_id: str | None = Field(
        None,
        description="Optional assignments._id to list only that task's students; omit for all your assignments",
    )


class PortalRecordUpdateInput(BaseModel):
    """Permission-checked portal writes (grades today; more entity.operation pairs later)."""

    actor_user_id: str = Field(..., description="Logged-in user's Mongo _id (teacher id from session)")
    actor_role: str = Field(
        "teacher",
        description="Portal role; must be allowed for this entity.operation (e.g. teacher for grade)",
    )
    entity: str = Field(
        ...,
        description="Resource type, e.g. assignment_submission",
    )
    operation: str = Field(
        ...,
        description="Action, e.g. grade (sets marks_obtained, feedback, graded, graded_at)",
    )
    submission_id: str | None = Field(
        None,
        description="assignment_submissions._id (preferred) — XOR with assignment_id+student_roll",
    )
    assignment_id: str | None = Field(None, description="With student_roll if no submission_id")
    student_roll: str | None = Field(None, description="e.g. CS-2024-009")
    marks_obtained: float | None = Field(None, description="For operation=grade (required unless in updates_json)")
    feedback: str | None = Field(None, max_length=8000)
    updates_json: str | None = Field(
        None,
        description='Optional JSON object merged into payload, e.g. {"marks_obtained": 85, "feedback": "..."}',
    )
    confirmed: bool = Field(
        False,
        description=(
            "For grade/delete: false first — if the tool returns needs_confirmation, ask the user yes/no; "
            "on yes, call again with true. Superadmin may omit (treated as bypass in backend)."
        ),
    )


class SuperadminDirectoryInput(BaseModel):
    """Superadmin-only: search or update/delete person records (students, teachers, admins, superadmins)."""

    actor_user_id: str = Field(
        ...,
        description="Superadmin session id (same as superadmin_portal_task student_id / context id).",
    )
    actor_role: str = Field("superadmin", description="Must be superadmin")
    operation: str = Field(
        ...,
        description="search = list matches; update = $set whitelisted fields; delete = remove row (needs confirmed=true after user says yes)",
    )
    target_collection: str = Field(
        "auto",
        description="auto searches all directory collections, or one of: students, teachers, admins, superadmins",
    )
    match_full_name: str | None = Field(None, description="Exact full name match (case-insensitive), e.g. Shuaib Asghar")
    match_email: str | None = None
    match_roll_number: str | None = Field(None, description="Student roll number")
    match_employee_id: str | None = Field(None, description="Staff employee_id")
    match_document_id: str | None = Field(None, description="24-char Mongo _id when collection is unknown")
    document_id: str | None = Field(
        None,
        description="Use with target_collection_for_id for direct row access (skips name search)",
    )
    target_collection_for_id: str | None = Field(
        None,
        description="Required with document_id: students | teachers | admins | superadmins",
    )
    updates_json: str | None = Field(
        None,
        description='For operation=update: JSON object of allowed fields only, e.g. {"full_name": "Shuaib Ahmed"}',
    )
    confirmed: bool = Field(
        False,
        description="For delete: set true after user confirms yes. Superadmin updates do not require this.",
    )


class ExportPortalDataInput(BaseModel):
    """Build a permission-checked download file and return a signed URL (see export kinds in backend)."""

    actor_user_id: str = Field(..., description="Session user id (student_id / teacher id / superadmin id from context)")
    actor_role: str = Field(
        ..., description="student | superadmin (other roles may be denied for a given kind)"
    )
    export_kind: str = Field(
        "semester_grades_detail",
        description=(
            "semester_grades_detail=one student's grade rows. "
            "all_students_profile=superadmin: full students directory. "
            "students_by_semester=superadmin: filter by students.semester; set filter_semester (e.g. 3)"
        ),
    )
    file_format: str = Field("csv", description="csv | txt | pdf")
    target_student_id: str | None = Field(
        None,
        description="For semester_grades_detail: superadmin must set target. Omit for own-data student export. Not used for all_students_profile / students_by_semester.",
    )
    filter_semester: int | None = Field(
        None,
        description="For students_by_semester only: program semester number (e.g. 3 for 3rd semester).",
    )


class PortalReadQueryInput(BaseModel):
    """Admin/superadmin: safe read (count/list) on a MongoDB collection using a JSON find filter."""

    actor_user_id: str = Field(
        ...,
        description="From task context, e.g. {student_id} of the logged-in admin/superadmin",
    )
    actor_role: str = Field(..., description="admin or superadmin")
    collection: str = Field(
        ...,
        description="Exact collection: **staff** = exam/admin/library/IT and other non-faculty employees; **teachers** = teaching faculty only; **users** = login roles. Also: library, students, challans, …",
    )
    operation: str = Field(
        ...,
        description="count = match count; find = list rows; distinct = unique values of one field (set distinct_field)",
    )
    query_json: str | None = Field(
        None,
        description='Mongo find filter, e.g. {"role": {"$ne": "student"}} on **users** for all non-student accounts. Use **$ne** / **$nin** / **$regex** as needed — do not approximate by adding separate counts. For **staff** in library/hostel: filter **staff** by department/role; library **books** = collection `library`.',
    )
    limit: int | None = Field(50, description="For find, max documents (capped at 200)")
    sort_key: str | None = Field(None, description="Optional field name to sort by for find")
    sort_dir: int = Field(1, description="1 ascending, -1 descending")
    distinct_field: str | None = Field(
        None,
        description="For operation=distinct only: one field name, e.g. role (lists unique values with optional query_json).",
    )


class CourseQueryInput(BaseModel):
    """Input schema for course-specific queries."""
    student_id: str = Field(..., description="The MongoDB ObjectId of the student")
    course_code: str | None = Field(None, description="Specific course code (optional)")


# ═══════════════════════════════════════════════════════════════════
# Student Info Tool
# ═══════════════════════════════════════════════════════════════════

class StudentInfoTool(BaseTool):
    name: str = "get_student_info"
    description: str = """
    Get basic profile: student (roll, semester, CGPA), teacher (employee ID,
    courses taught), admin (role, department), or superadmin.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        
        if student:
            return {
                "user_role": "student",
                "student_id": str(student["_id"]),
                "full_name": student.get("full_name"),
                "roll_number": student.get("roll_number"),
                "email": student.get("email"),
                "semester": student.get("semester"),
                "department": student.get("department"),
                "batch": student.get("batch"),
                "cgpa": student.get("cgpa"),
                "status": student.get("status"),
                "current_fee_status": student.get("current_fee_status"),
                "hostel": student.get("hostel"),
            }
        
        teacher = find_teacher(db, student_id)
        if teacher:
            return {
                "user_role": "teacher",
                "teacher_id": str(teacher["_id"]),
                "full_name": teacher.get("full_name"),
                "employee_id": teacher.get("employee_id"),
                "email": teacher.get("email"),
                "department": teacher.get("department"),
                "designation": teacher.get("designation"),
                "assigned_course_codes": teacher.get("assigned_course_codes", []),
                "status": teacher.get("status"),
            }

        admin = find_admin(db, student_id)
        if admin:
            return {
                "user_role": "admin",
                "admin_id": str(admin["_id"]),
                "full_name": admin.get("full_name"),
                "email": admin.get("email"),
                "department": admin.get("department", ""),
                "role": admin.get("role", "admin"),
                "employee_id": admin.get("employee_id", ""),
            }

        superadmin = find_superadmin(db, student_id)
        if superadmin:
            return {
                "user_role": "superadmin",
                "superadmin_id": str(superadmin["_id"]),
                "full_name": superadmin.get("full_name"),
                "email": superadmin.get("email"),
                "department": superadmin.get("department", "") or "System",
                "employee_id": superadmin.get("employee_id", ""),
            }

        return {"error": f"User not found with identifier: {student_id}"}


# ═══════════════════════════════════════════════════════════════════
# Assignment Query Tool
# ═══════════════════════════════════════════════════════════════════

class PortalDownloadLinkInput(BaseModel):
    """Resolve authorized portal PDF download links from the user's natural-language request."""

    user_id: str = Field(
        ...,
        description="MongoDB ObjectId of the logged-in user (task context: student_id; for faculty, same field holds teacher _id).",
    )
    user_role: str = Field(
        ...,
        description="Exactly 'student' or 'teacher' for the current session.",
    )
    search_query: str = Field(
        "",
        description=(
            "Their words: topic, course code, assignment/handout/syllabus name, or vague reference "
            "('wo PDF', 'us document ka link'). Empty string = most recent downloadable materials they may access."
        ),
    )


class PortalDownloadLinkTool(BaseTool):
    name: str = "find_portal_downloads"
    description: str = """
    Use whenever the user wants a downloadable file, PDF, or shareable link from the portal
    in natural language: assignment brief, course handout, class material, syllabus-style PDF,
    'document bhejo', 'PDF do', 'link send karo', 'WhatsApp pe bhejo', 'file share karo',
    or any similar request—not only the word "assignment".
    Returns time-limited signed URLs for PDFs they are authorized to access (students: enrolled
    courses; teachers: materials they published). These links are for course/portal PDFs only:
    they are NOT transcripts, enrollment certificates, or admit cards—if the user clearly means
    those official documents, use the records/fee tools instead (or explain the difference gently).
    Always pass search_query distilled from their message; use "" if they only want the latest links.
    """
    args_schema: Type[BaseModel] = PortalDownloadLinkInput

    def _run(self, user_id: str, user_role: str, search_query: str = "") -> dict:
        from services.assignment_upload_service import get_authorized_portal_downloads

        return get_authorized_portal_downloads(
            user_id=user_id,
            user_role=user_role,
            search_query=search_query or "",
            limit=5,
        )


class AssignmentQueryTool(BaseTool):
    name: str = "query_assignments"
    description: str = """
    Query assignments for a student. Returns pending, upcoming, overdue, and submitted
    work. Lists are sorted with the most recently *posted* assignment first within each
    bucket (uses created_at / upload time, not due date). For "latest/newest/last pending"
    questions, use **newest_incomplete_assignment** (not-yet-submitted work, newest upload first).
    **assignment_brief_pdf_url** is a time-limited portal link when a brief PDF exists.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        
        # Get student's enrolled courses
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        
        student_oid = student["_id"]
        sid_str = str(student_oid)
        current_semester = semester or student.get("semester")
        dept = student.get("department")

        # Courses for this student's department + semester (multi-department DB safe)
        course_query: dict = {"semester": current_semester}
        if dept:
            course_query["department"] = dept
        courses = list(db["courses"].find(course_query))
        course_ids = [c["_id"] for c in courses]
        course_map = {str(c["_id"]): c for c in courses}
        
        # Get assignments for these courses
        assignments = list(db["assignments"].find({"course_id": {"$in": course_ids}}))
        
        # Get submissions for this student (sort by submitted_at desc so most recent first)
        assignment_ids = [a["_id"] for a in assignments]
        submissions = list(db["assignment_submissions"].find({
            "student_id": student_oid,
            "assignment_id": {"$in": assignment_ids}
        }).sort("submitted_at", -1))
        submission_map = {str(s["assignment_id"]): s for s in submissions}
        
        now = datetime.now()
        if now.tzinfo is None:
            now_utc = now.replace(tzinfo=timezone.utc)
        else:
            now_utc = now.astimezone(timezone.utc)

        def due_cmp(due) -> datetime | None:
            if due is None:
                return None
            if getattr(due, "tzinfo", None) is None:
                return due.replace(tzinfo=timezone.utc)
            return due.astimezone(timezone.utc)

        result = {
            "pending": [],
            "submitted": [],
            "overdue": [],
            "upcoming": [],
        }
        
        for a in assignments:
            aid = str(a["_id"])
            course = course_map.get(str(a["course_id"]), {})
            sub = submission_map.get(aid)
            rec_ts = _assignment_upload_recency_ts(a)
            posted_iso = datetime.fromtimestamp(rec_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            assignment_info: dict[str, Any] = {
                "assignment_id": aid,
                "title": a.get("title"),
                "course_name": course.get("course_name"),
                "course_code": a.get("course_code"),
                "due_date": a.get("due_date").strftime("%Y-%m-%d %H:%M") if a.get("due_date") else None,
                "total_marks": a.get("total_marks"),
                "has_pdf_brief": assignment_has_downloadable_pdf(a),
                "source": a.get("source"),
                "assignment_posted_at": posted_iso,
                "_recency_ts": rec_ts,
                "assignment_brief_pdf_url": None,
            }
            if assignment_info["has_pdf_brief"]:
                try:
                    tok = mint_assignment_download_token(sid_str, "student", aid)
                    assignment_info["assignment_brief_pdf_url"] = build_signed_assignment_url(
                        tok, None
                    )
                except Exception:
                    assignment_info["assignment_brief_pdf_url"] = None
            
            due_u = due_cmp(a.get("due_date"))

            if sub:
                assignment_info["status"] = sub.get("status")
                assignment_info["marks_obtained"] = sub.get("marks_obtained")
                assignment_info["submitted_at"] = sub.get("submitted_at").strftime("%Y-%m-%d") if sub.get("submitted_at") else None
                assignment_info["feedback"] = sub.get("feedback")
                
                if sub.get("status") == "submitted":
                    result["submitted"].append(assignment_info)
                elif sub.get("status") == "overdue":
                    assignment_info["bucket"] = "overdue"
                    result["overdue"].append(assignment_info)
                else:
                    if due_u and due_u > now_utc:
                        assignment_info["bucket"] = "pending"
                        result["pending"].append(assignment_info)
                    else:
                        assignment_info["bucket"] = "overdue"
                        result["overdue"].append(assignment_info)
            else:
                if due_u and due_u > now_utc:
                    days_left = (due_u - now_utc).days
                    assignment_info["days_until_due"] = days_left
                    if days_left > 7:
                        assignment_info["bucket"] = "upcoming"
                        result["upcoming"].append(assignment_info)
                    else:
                        assignment_info["bucket"] = "pending"
                        result["pending"].append(assignment_info)
                else:
                    assignment_info["bucket"] = "overdue"
                    result["overdue"].append(assignment_info)

        def sort_newest_upload_first(lst: list) -> None:
            lst.sort(key=lambda x: x.get("_recency_ts", 0), reverse=True)

        sort_newest_upload_first(result["pending"])
        sort_newest_upload_first(result["upcoming"])
        sort_newest_upload_first(result["overdue"])

        incomplete_merged = result["pending"] + result["upcoming"] + result["overdue"]
        incomplete_merged.sort(key=lambda x: x.get("_recency_ts", 0), reverse=True)
        result["incomplete_assignments_newest_first"] = [
            _strip_internal_assignment_fields({**x}) for x in incomplete_merged
        ]
        result["newest_incomplete_assignment"] = (
            result["incomplete_assignments_newest_first"][0]
            if result["incomplete_assignments_newest_first"]
            else None
        )

        for lst in (result["pending"], result["upcoming"], result["overdue"], result["submitted"]):
            for i, row in enumerate(lst):
                lst[i] = _strip_internal_assignment_fields(row)
        result["guidance"] = (
            'For "last/latest/most recent pending" (newest on the portal), answer using '
            "newest_incomplete_assignment — that is by assignment upload time, not due date. "
            "When the student wants the PDF, include assignment_brief_pdf_url from that row."
        )

        result["summary"] = {
            "total_pending": len(result["pending"]),
            "total_submitted": len(result["submitted"]),
            "total_overdue": len(result["overdue"]),
            "total_upcoming": len(result["upcoming"]),
            "total_incomplete": len(result["incomplete_assignments_newest_first"]),
        }
        
        return result


# ═══════════════════════════════════════════════════════════════════
# Fee Query Tool
# ═══════════════════════════════════════════════════════════════════

class FeeQueryTool(BaseTool):
    name: str = "query_fees"
    description: str = """
    Query fee status for a student. Returns current semester fee status,
    payment history, pending dues, and whether the student can access documents.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        
        student_oid = student["_id"]
        
        # Get all fee records for this student
        fee_records = list(db["fees"].find(
            {"student_id": student_oid}
        ).sort("semester", 1))
        
        current_semester = semester or student.get("semester")
        current_fee = None
        total_paid = 0
        total_due = 0
        
        history = []
        for fee in fee_records:
            record = {
                "semester": fee.get("semester"),
                "amount_due": fee.get("amount_due"),
                "amount_paid": fee.get("amount_paid"),
                "balance": fee.get("balance"),
                "status": fee.get("status"),
                "payment_date": fee.get("payment_date").strftime("%Y-%m-%d") if fee.get("payment_date") else None,
                "challan_number": fee.get("challan_number"),
            }
            history.append(record)
            total_paid += fee.get("amount_paid", 0)
            total_due += fee.get("amount_due", 0)
            
            if fee.get("semester") == current_semester:
                current_fee = record
        
        # Check if student can access documents (all fees must be paid)
        has_pending_dues = any(f.get("status") in ["unpaid", "partial"] for f in fee_records)
        
        return {
            "student_name": student.get("full_name"),
            "current_semester": current_semester,
            "current_fee_status": current_fee,
            "payment_history": history,
            "total_paid_all_time": total_paid,
            "total_dues_all_time": total_due,
            "has_pending_dues": has_pending_dues,
            "can_access_documents": not has_pending_dues,
            "message": "Please clear your pending dues to access documents." if has_pending_dues else "All fees are clear. You can request documents.",
        }


# ═══════════════════════════════════════════════════════════════════
# Exam Query Tool
# ═══════════════════════════════════════════════════════════════════

class ExamQueryTool(BaseTool):
    name: str = "query_exams"
    description: str = """
    Query exam schedule for a student. Returns upcoming mid-term and final exams
    with dates, times, and venues. Shows which exam is first.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        
        current_semester = semester or student.get("semester")
        dept = student.get("department")
        now = datetime.now()

        exam_filter: dict = {
            "semester": current_semester,
            "exam_date": {"$gte": now},
        }
        if dept:
            exam_filter["department"] = dept
        exams = list(db["exams"].find(exam_filter).sort("exam_date", 1))
        
        # Get course details
        course_ids = list(set(e.get("course_id") for e in exams))
        courses = {str(c["_id"]): c for c in db["courses"].find({"_id": {"$in": course_ids}})}
        
        mid_exams = []
        final_exams = []
        
        for exam in exams:
            course = courses.get(str(exam.get("course_id")), {})
            exam_date = exam.get("exam_date")
            days_until = (exam_date - now).days if exam_date else None
            
            exam_info = {
                "course_name": course.get("course_name"),
                "course_code": exam.get("course_code"),
                "exam_type": exam.get("exam_type"),
                "exam_date": exam_date.strftime("%Y-%m-%d") if exam_date else None,
                "day_name": exam_date.strftime("%A") if exam_date else None,
                "start_time": exam.get("start_time"),
                "venue": exam.get("venue"),
                "duration_minutes": exam.get("duration_minutes"),
                "days_until_exam": days_until,
            }
            
            if exam.get("exam_type") == "mid":
                mid_exams.append(exam_info)
            else:
                final_exams.append(exam_info)
        
        first_exam = exams[0] if exams else None
        first_exam_info = None
        if first_exam:
            course = courses.get(str(first_exam.get("course_id")), {})
            first_exam_info = {
                "course_name": course.get("course_name"),
                "course_code": first_exam.get("course_code"),
                "exam_type": first_exam.get("exam_type"),
                "exam_date": first_exam.get("exam_date").strftime("%Y-%m-%d"),
                "start_time": first_exam.get("start_time"),
                "venue": first_exam.get("venue"),
            }
        
        return {
            "student_name": student.get("full_name"),
            "semester": current_semester,
            "first_upcoming_exam": first_exam_info,
            "mid_term_exams": mid_exams,
            "final_exams": final_exams,
            "total_upcoming_exams": len(exams),
        }


# ═══════════════════════════════════════════════════════════════════
# Grade Query Tool
# ═══════════════════════════════════════════════════════════════════

class GradeQueryTool(BaseTool):
    name: str = "query_grades"
    description: str = """
    Query academic grades for a student. Returns grades by semester,
    individual course results, and CGPA.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        
        student_oid = student["_id"]
        
        # Build query
        query = {"student_id": student_oid}
        if semester:
            query["semester"] = semester
        
        grades = list(db["grades"].find(query).sort([("semester", 1), ("course_code", 1)]))
        
        # Group by semester
        semesters = {}
        for grade in grades:
            sem = grade.get("semester")
            if sem not in semesters:
                semesters[sem] = {
                    "courses": [],
                    "total_gpa_points": 0,
                    "total_credit_hours": 0,
                }
            
            semesters[sem]["courses"].append({
                "course_code": grade.get("course_code"),
                "mid_marks": grade.get("mid_marks"),
                "final_marks": grade.get("final_marks"),
                "total_marks": grade.get("total_marks"),
                "out_of": grade.get("out_of"),
                "grade_letter": grade.get("grade_letter"),
                "gpa_points": grade.get("gpa_points"),
            })
            semesters[sem]["total_gpa_points"] += grade.get("gpa_points", 0)
            semesters[sem]["total_credit_hours"] += 3  # Assuming 3 credit hours per course
        
        # Calculate semester GPAs
        result_semesters = []
        for sem, data in sorted(semesters.items()):
            num_courses = len(data["courses"])
            semester_gpa = data["total_gpa_points"] / num_courses if num_courses > 0 else 0
            result_semesters.append({
                "semester": sem,
                "courses": data["courses"],
                "semester_gpa": round(semester_gpa, 2),
            })
        
        return {
            "student_name": student.get("full_name"),
            "roll_number": student.get("roll_number"),
            "current_cgpa": student.get("cgpa"),
            "semesters": result_semesters,
            "total_semesters_completed": len(result_semesters),
        }


# ═══════════════════════════════════════════════════════════════════
# Attendance, Timetable, Admit cards, Records, Library, Scholarship,
# Hostel, Complaints, Announcements (iba_sukkur_data / new_dummy_data)
# ═══════════════════════════════════════════════════════════════════


class AttendanceQueryTool(BaseTool):
    name: str = "query_attendance"
    description: str = """
    Class attendance for the student: percentage per course, status (good/warning/critical).
    Use when they ask about attendance, shortage, 75% rule, or class presence.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        oid = student["_id"]
        sem = semester or student.get("semester")
        q = {"student_id": oid}
        if sem is not None:
            q["semester"] = sem
        rows = list(db["attendance"].find(q).sort("course_code", 1))
        items = []
        for r in rows:
            items.append(
                {
                    "course_code": r.get("course_code"),
                    "total_classes": r.get("total_classes"),
                    "attended": r.get("attended"),
                    "absent": r.get("absent"),
                    "percentage": r.get("percentage"),
                    "status": r.get("status"),
                }
            )
        return {
            "student_name": student.get("full_name"),
            "semester_filter": sem,
            "courses": items,
            "count": len(items),
        }


class TimetableQueryTool(BaseTool):
    name: str = "query_timetable"
    description: str = """
    Weekly class timetable with course and instructor context for the student's
    department and semester.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        dept = student.get("department")
        sem = semester or student.get("semester")
        q = {"department": dept, "semester": sem}
        slots = list(
            db["timetable"]
            .find(q)
            .sort([("day_num", 1), ("start", 1)])
        )

        course_ids = [s.get("course_id") for s in slots if s.get("course_id")]
        course_docs = list(db["courses"].find({"_id": {"$in": course_ids}})) if course_ids else []
        course_map = {str(c["_id"]): c for c in course_docs}

        course_codes = [s.get("course_code") for s in slots if s.get("course_code")]
        teacher_rows = list(db["course_teacher_map"].find({"course_code": {"$in": course_codes}})) if course_codes else []
        teacher_map = {r.get("course_code"): r for r in teacher_rows}

        items = []
        for s in slots:
            course_doc = course_map.get(str(s.get("course_id")), {})
            teacher_doc = teacher_map.get(s.get("course_code"), {})
            items.append(
                {
                    "course_code": s.get("course_code"),
                    "course_name": course_doc.get("course_name"),
                    "teacher_name": teacher_doc.get("teacher_name"),
                    "day": s.get("day"),
                    "start": s.get("start"),
                    "end": s.get("end"),
                    "room": s.get("room"),
                }
            )
        return {
            "student_name": student.get("full_name"),
            "department": dept,
            "semester": sem,
            "slots": items,
            "count": len(items),
        }


class CourseTeacherQueryTool(BaseTool):
    name: str = "query_course_teachers"
    description: str = """
    Current semester course list with assigned teachers for the student's department.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}

        dept = student.get("department")
        sem = semester or student.get("semester")
        course_docs = list(db["courses"].find({"department": dept, "semester": sem}))
        course_codes = [c.get("course_code") for c in course_docs if c.get("course_code")]
        teacher_rows = list(db["course_teacher_map"].find({"course_code": {"$in": course_codes}})) if course_codes else []
        teacher_map = {r.get("course_code"): r for r in teacher_rows}

        items = []
        for c in course_docs:
            code = c.get("course_code")
            teacher_doc = teacher_map.get(code, {})
            items.append(
                {
                    "course_code": code,
                    "course_name": c.get("course_name"),
                    "teacher_name": teacher_doc.get("teacher_name"),
                    "semester": c.get("semester"),
                    "department": c.get("department"),
                }
            )

        return {
            "student_name": student.get("full_name"),
            "department": dept,
            "semester": sem,
            "courses": items,
            "count": len(items),
        }


class AdmitCardQueryTool(BaseTool):
    name: str = "query_admit_cards"
    description: str = """
    Exam admit cards / hall tickets: readiness, seat number, venue, blocked_reason (e.g. fee_unpaid).
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        oid = student["_id"]
        sem = semester or student.get("semester")
        q: dict = {"student_id": oid}
        if sem is not None:
            q["semester"] = sem
        rows = list(db["admit_cards"].find(q).sort([("exam_date", 1)]))
        cards = []
        for r in rows:
            ed = r.get("exam_date")
            cards.append(
                {
                    "course_code": r.get("course_code"),
                    "exam_type": r.get("exam_type"),
                    "exam_date": ed.strftime("%Y-%m-%d") if ed else None,
                    "venue": r.get("venue"),
                    "seat_number": r.get("seat_number"),
                    "is_ready": r.get("is_ready"),
                    "blocked_reason": r.get("blocked_reason"),
                }
            )
        return {
            "student_name": student.get("full_name"),
            "admit_cards": cards,
            "count": len(cards),
        }


class RecordsQueryTool(BaseTool):
    name: str = "query_student_records"
    description: str = """
    Official records: transcript request status and enrollment (or other) certificate status,
    blocked_reason if fee unpaid. Not raw grades — use grade tool for marks.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        oid = student["_id"]
        tr = list(db["transcripts"].find({"student_id": oid}).sort("requested_at", -1).limit(5))
        cert = list(db["certificates"].find({"student_id": oid}).sort("requested_at", -1).limit(5))

        def _strip(docs, label):
            out = []
            for x in docs:
                out.append(
                    {
                        "type": label,
                        "status": x.get("status"),
                        "blocked_reason": x.get("blocked_reason"),
                        "ticket_number": x.get("ticket_number"),
                    }
                )
            return out

        return {
            "student_name": student.get("full_name"),
            "transcripts": _strip(tr, "transcript"),
            "certificates": _strip(cert, "certificate"),
        }


class LibraryQueryTool(BaseTool):
    name: str = "query_library"
    description: str = """
    Library books issued to the student: title, due date, overdue fines, returned status.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        oid = student["_id"]
        rows = list(db["library"].find({"student_id": oid}).sort("issued_date", -1).limit(25))
        books = []
        for r in rows:
            dd = r.get("due_date")
            books.append(
                {
                    "book_title": r.get("book_title"),
                    "author": r.get("author"),
                    "status": r.get("status"),
                    "issued_date": r.get("issued_date").strftime("%Y-%m-%d") if r.get("issued_date") else None,
                    "due_date": dd.strftime("%Y-%m-%d") if dd else None,
                    "fine_amount": r.get("fine_amount"),
                }
            )
        return {"student_name": student.get("full_name"), "books": books, "count": len(books)}


class ScholarshipQueryTool(BaseTool):
    name: str = "query_scholarships"
    description: str = """
    Scholarships: name, provider, amount, status (active/applied/expired), disbursement dates.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        oid = student["_id"]
        rows = list(db["scholarships"].find({"student_id": oid}))
        items = []
        for r in rows:
            nd = r.get("next_disbursement")
            items.append(
                {
                    "scholarship_name": r.get("scholarship_name"),
                    "provider": r.get("provider"),
                    "amount_per_semester": r.get("amount_per_semester"),
                    "status": r.get("status"),
                    "next_disbursement": nd.strftime("%Y-%m-%d") if nd else None,
                }
            )
        return {"student_name": student.get("full_name"), "scholarships": items, "count": len(items)}


class HostelQueryTool(BaseTool):
    name: str = "query_hostel"
    description: str = """
    Hostel allotment: room, monthly fee, warden, check-in if the student has a hostel record.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        oid = student["_id"]
        r = db["hostel"].find_one({"student_id": oid})
        if not r:
            return {
                "student_name": student.get("full_name"),
                "has_hostel": False,
                "message": "No hostel allotment on record.",
            }
        return {
            "student_name": student.get("full_name"),
            "has_hostel": True,
            "room_number": r.get("room_number"),
            "monthly_fee": r.get("monthly_fee"),
            "warden": r.get("warden"),
            "status": r.get("status"),
        }


class ComplaintQueryTool(BaseTool):
    name: str = "query_complaints"
    description: str = """
    Student's support tickets / complaints: type, status, ticket number, staff response.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        oid = student["_id"]
        rows = list(
            db["complaints"]
            .find({"student_id": oid})
            .sort("submitted_at", -1)
            .limit(20)
        )
        items = []
        for r in rows:
            items.append(
                {
                    "type": r.get("type"),
                    "subject": r.get("subject"),
                    "status": r.get("status"),
                    "ticket_number": r.get("ticket_number"),
                    "response": r.get("response"),
                }
            )
        return {"student_name": student.get("full_name"), "complaints": items, "count": len(items)}


class TeacherTeachingQueryTool(BaseTool):
    name: str = "query_teacher_teaching"
    description: str = """
    Faculty-only: assignments this teacher created, with submission counts
    (pending / submitted / overdue / graded). Pass the teacher's portal user id
    (MongoDB teachers._id string from session).
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        teacher = find_teacher(db, student_id)
        if not teacher:
            return {"error": f"Teacher not found with identifier: {student_id}"}
        tid = teacher["_id"]
        assigns = list(
            db["assignments"]
            .find({"created_by_teacher": tid})
            .sort("due_date", 1)
            .limit(80)
        )
        items = []
        for a in assigns:
            aid = a["_id"]
            total = db["assignment_submissions"].count_documents({"assignment_id": aid})
            pending = db["assignment_submissions"].count_documents(
                {"assignment_id": aid, "status": "pending"}
            )
            submitted = db["assignment_submissions"].count_documents(
                {"assignment_id": aid, "status": "submitted"}
            )
            overdue = db["assignment_submissions"].count_documents(
                {"assignment_id": aid, "status": "overdue"}
            )
            graded = db["assignment_submissions"].count_documents(
                {"assignment_id": aid, "graded": True}
            )
            dd = a.get("due_date")
            items.append(
                {
                    "assignment_id": str(a["_id"]),
                    "course_code": a.get("course_code"),
                    "title": a.get("title"),
                    "total_marks": a.get("total_marks"),
                    "due_date": dd.strftime("%Y-%m-%d") if dd else None,
                    "is_active": a.get("is_active"),
                    "submissions_total": total,
                    "pending": pending,
                    "submitted": submitted,
                    "overdue": overdue,
                    "graded_count": graded,
                }
            )
        return {
            "teacher_name": teacher.get("full_name"),
            "assignments": items,
            "count": len(items),
        }


class TeacherSubmissionRosterTool(BaseTool):
    name: str = "query_teacher_submission_roster"
    description: str = """
    Faculty-only: full roster per assignment — each student's status, submitted_at, marks,
    and **submitted_work_pdf_url** (time-limited) for the file they **turned in** — NOT the
    assignment brief. For the brief/handout PDF use find_portal_downloads instead.
    Pass teacher user id from session; assignment_id from query_teacher_teaching to focus one task.
    """
    args_schema: Type[BaseModel] = TeacherSubmissionsInput

    def _run(self, teacher_id: str, assignment_id: str | None = None) -> dict:
        try:
            return teacher_submissions_overview(teacher_id, assignment_id)
        except PermissionError as e:
            return {"error": str(e)}
        except ValueError as e:
            return {"error": str(e)}


class PortalRecordUpdateTool(BaseTool):
    name: str = "portal_record_update"
    description: str = """
    Permission-checked update to portal data. Each entity.operation checks the actor's role and
    row ownership before writing (superadmin skips ownership on grade).

    Current support:
    - entity=assignment_submission, operation=grade — teacher must be submission.teacher_id (unless superadmin).
      Provide submission_id OR assignment_id+student_roll; marks_obtained required; feedback optional.
      Also accepts updates_json for the same fields. If needs_confirmation is returned, ask the user
      to confirm (yes/no) then call again with confirmed=true.

    - entity=assignment_submission, operation=delete — superadmin only; removes row and stored PDF.
      Same lookup as grade; requires confirmation for non-superadmin (always denied); superadmin is audited.

    For grading, prefer submission_id from query_teacher_submission_roster.
    """
    args_schema: Type[BaseModel] = PortalRecordUpdateInput

    def _run(
        self,
        actor_user_id: str,
        actor_role: str = "teacher",
        entity: str = "",
        operation: str = "",
        submission_id: str | None = None,
        assignment_id: str | None = None,
        student_roll: str | None = None,
        marks_obtained: float | None = None,
        feedback: str | None = None,
        updates_json: str | None = None,
        confirmed: bool = False,
    ) -> dict:
        payload: dict = {}
        if marks_obtained is not None:
            payload["marks_obtained"] = marks_obtained
        if feedback is not None:
            payload["feedback"] = feedback
        try:
            return portal_record_update(
                actor_role=actor_role,
                actor_user_id=actor_user_id,
                entity=entity,
                operation=operation,
                lookup={
                    "submission_id": submission_id,
                    "assignment_id": assignment_id,
                    "student_roll": student_roll,
                },
                payload=payload,
                updates_json=updates_json,
                confirmed=confirmed,
            )
        except PermissionError as e:
            return {"error": str(e), "permission_denied": True}
        except ValueError as e:
            return {"error": str(e)}


class SuperadminDirectoryTool(BaseTool):
    name: str = "superadmin_directory"
    description: str = """
    Superadmin only: search, update, or delete person rows in students, teachers, admins, or superadmins.

    **To rename or fix a profile (e.g. Shuaib Asghar → Shuaib Ahmed):**
    1) operation=search, match_full_name="Shuaib Asghar" (or match_email / roll / employee_id). If one match, note collection + document_id.
    2) operation=update, same match fields **or** document_id + target_collection_for_id, updates_json: {"full_name": "Shuaib Ahmed"}.

    **Whitelisted fields only** (no passwords). Unsupported fields are rejected. Deletes require confirmed=true
    after the user says yes, unless your policy treats superadmin as already authorized (the tool will return
    needs_confirmation until confirmed=true for delete).
    """
    args_schema: Type[BaseModel] = SuperadminDirectoryInput

    def _run(
        self,
        actor_user_id: str,
        actor_role: str = "superadmin",
        operation: str = "",
        target_collection: str = "auto",
        match_full_name: str | None = None,
        match_email: str | None = None,
        match_roll_number: str | None = None,
        match_employee_id: str | None = None,
        match_document_id: str | None = None,
        document_id: str | None = None,
        target_collection_for_id: str | None = None,
        updates_json: str | None = None,
        confirmed: bool = False,
    ) -> dict:
        try:
            return run_superadmin_directory_op(
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                operation=operation,
                target_collection=target_collection,
                match_full_name=match_full_name,
                match_email=match_email,
                match_roll_number=match_roll_number,
                match_employee_id=match_employee_id,
                match_document_id=match_document_id,
                document_id=document_id,
                target_collection_for_id=target_collection_for_id,
                updates_json=updates_json,
                confirmed=confirmed,
            )
        except PermissionError as e:
            return {"error": str(e), "permission_denied": True}
        except ValueError as e:
            return {"error": str(e)}


class ExportPortalDataTool(BaseTool):
    name: str = "export_portal_data"
    description: str = """
    Generate a downloadable file (CSV, plain text, or PDF) and return a **signed, time-limited** link.

    Kinds (superadmin):
    - **all_students_profile** — one row per student, profile fields (name, email, roll, semester, dept, etc.).
      No target_student_id. Use for "all students list CSV".
    - **students_by_semester** — same, but only where `students.semester` == **filter_semester** (e.g. 3).
      Set filter_semester. Use for "all third semester students".
    - **semester_grades_detail** — one student's detailed grade table; superadmin must set **target_student_id**
      (or student exports own: omit target).

    Students: only **semester_grades_detail** (own data). On success, echo **download_url** in the reply.
    """
    args_schema: Type[BaseModel] = ExportPortalDataInput

    def _run(
        self,
        actor_user_id: str,
        actor_role: str,
        export_kind: str = "semester_grades_detail",
        file_format: str = "csv",
        target_student_id: str | None = None,
        filter_semester: int | None = None,
    ) -> dict:
        try:
            return run_export_for_chat(
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                export_kind=export_kind,
                file_format=file_format,
                target_student_id=target_student_id,
                filter_semester=filter_semester,
            )
        except PermissionError as e:
            return {"error": str(e), "permission_denied": True, "success": False}
        except ValueError as e:
            return {"error": str(e), "success": False}


class PortalReadQueryTool(BaseTool):
    name: str = "portal_read_query"
    description: str = """
    **Admin / superadmin:** answer "how many", "list", "count", or "filter" questions against the **database**
    using a single generic read. Pass **collection** and **operation** `count`, `find`, or `distinct`.

    **CRITICAL — `teachers` is NOT all employees:** The **`teachers`** collection is **teaching faculty only** (instructors
    in departments). **Exam staff, admin office, library desk, IT, finance, admission, and similar roles** are **not**
    stored in `teachers`. They are in the **`staff`** collection (one document per person: `department`, `role` like
    `exam_staff`, `admin_staff`, `library_staff`, `hostel_staff`, `finance_staff`, `admission_staff`, `it_staff`, …) and
    their portal accounts sit in **`users`** with the same or related **`role`**. To answer "where are other staff" or
    "exam/admin staff", you **must** call **`staff`** and/or **`users`** — never infer "only teachers exist" from
    **`teachers` alone.**

    **Collection name** must match the **MongoDB collection** in this database (e.g. `library`, `students`,
    `challans`, `semester_results`, `student_course_teachers`, `teacher_student_relations`, `chat_logs`, `users` — not
    made-up names like `library_system`). **Superadmin**: any valid identifier. **Admin**: same collections as in
    Compass (allowlist in backend `READ_COLLECTIONS_ADMIN`).

    **query_json** — Mongo find filter, e.g.:
    - **Users whose role is not `student`:** `collection=users`, `operation=count`, `query_json={"role": {"$ne": "student"}}` — **never** sum separate student/teacher counts; staff use roles like `library_staff`, `hostel_staff`, `admin_staff`, and `superadmin` may exist — always use one **users** query or **operation=distinct** + **distinct_field=role** to see all roles.
    - CS students: `{"department": "CS"}` or regex on `department`
    - MATH: use the **latest** user message, not a previous department
    - **All support / non-faculty employees (exam, admin, library, etc.):** collection **`staff`** (count with `{}` or
    find; filter e.g. `{{"role": "exam_staff"}}` or `{{"department": "Examination"}}` as your data has it). If unsure,
    also **`users`** with **`distinct_field=role`** to see which non-`student` / non-`teacher` roles exist.
    - **Hostel / library desk (people):** **`staff`**, same as above — **not** the `hostel` or `library` collections.
    - **Library books and issue records:** collection **`library`**
    - **Teaching faculty only:** `teachers` — do **not** use this for exam/admin/library/IT staff questions.

    **Every time** the user changes department, role, or filter (including short follow-ups like "and in math"),
    call this tool **again** with updated `query_json`. Do **not** repeat a previous tool result for a new question.

    **count** returns a number; **find** returns rows; **distinct** + **distinct_field** returns unique values (e.g. all
    `role` values in `users`). Do not guess counts—call this tool.
    """
    args_schema: Type[BaseModel] = PortalReadQueryInput

    def _run(
        self,
        actor_user_id: str,
        actor_role: str,
        collection: str,
        operation: str,
        query_json: str | None = None,
        limit: int | None = 50,
        sort_key: str | None = None,
        sort_dir: int = 1,
        distinct_field: str | None = None,
    ) -> dict:
        try:
            return run_portal_read_query(
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                collection=collection,
                operation=operation,
                query_json=query_json,
                limit=limit,
                sort_key=sort_key,
                sort_dir=sort_dir,
                distinct_field=distinct_field,
            )
        except PermissionError as e:
            return {"error": str(e), "ok": False, "permission_denied": True}
        except ValueError as e:
            return {"error": str(e), "ok": False}


class AnnouncementQueryTool(BaseTool):
    name: str = "query_announcements"
    description: str = """
    Official campus announcements for the current user: students see
    all/department/hostel scoped notices; faculty by department; admins see all active.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        admin = find_admin(db, student_id)
        superadmin = find_superadmin(db, student_id) if not admin else None
        student = find_student(db, student_id)
        teacher = (
            find_teacher(db, student_id)
            if not student and not admin and not superadmin
            else None
        )

        if admin or superadmin:
            doc = admin if admin else superadmin
            display_name = doc.get("full_name", "Admin")
            raw = list(
                db["announcements"]
                .find({"is_active": True})
                .sort("posted_at", -1)
                .limit(30)
            )
            items = []
            for a in raw:
                pa = a.get("posted_at")
                items.append(
                    {
                        "title": a.get("title"),
                        "body": a.get("body"),
                        "category": a.get("category"),
                        "is_urgent": a.get("is_urgent"),
                        "posted_at": pa.strftime("%Y-%m-%d") if pa else None,
                    }
                )
            return {
                "user_name": display_name,
                "announcements": items[:20],
                "count": min(len(items), 20),
            }

        if student:
            dept = student.get("department")
            in_hostel = bool(student.get("hostel"))
            display_name = student.get("full_name")
        elif teacher:
            dept = teacher.get("department")
            in_hostel = False
            display_name = teacher.get("full_name")
        else:
            return {"error": f"User not found with identifier: {student_id}"}

        raw = list(db["announcements"].find({"is_active": True}).sort("posted_at", -1).limit(50))
        items = []
        for a in raw:
            tgt = a.get("target") or "all"
            if tgt == "all":
                include = True
            elif tgt == "department":
                include = dept in (a.get("departments") or [])
            elif tgt == "hostel":
                include = in_hostel
            else:
                include = False
            if not include:
                continue
            pa = a.get("posted_at")
            items.append(
                {
                    "title": a.get("title"),
                    "body": a.get("body"),
                    "category": a.get("category"),
                    "is_urgent": a.get("is_urgent"),
                    "posted_at": pa.strftime("%Y-%m-%d") if pa else None,
                }
            )
        return {
            "user_name": display_name,
            "announcements": items[:15],
            "count": min(len(items), 15),
        }


# ═══════════════════════════════════════════════════════════════════
# Semantic Search Tool
# ═══════════════════════════════════════════════════════════════════

class SemanticSearchInput(BaseModel):
    """Input schema for semantic search."""
    query: str = Field(..., description="The search query (e.g., 'machine learning assignment', 'database course')")
    collection: str = Field("assignments", description="Collection to search: 'courses' or 'assignments'")
    limit: int = Field(5, description="Number of results to return")


class SemanticSearchTool(BaseTool):
    name: str = "semantic_search"
    description: str = """
    Search for courses or assignments using natural language.
    Useful when the student asks about topics without knowing exact names.
    
    Examples:
    - "machine learning wala assignment" → finds NLP/ML related assignments
    - "database course" → finds Database Systems course
    - "programming assignment" → finds coding-related assignments
    """
    args_schema: Type[BaseModel] = SemanticSearchInput

    def _run(self, query: str, collection: str = "assignments", limit: int = 5) -> dict:
        try:
            from services.vector_store import get_vector_store_manager
            
            manager = get_vector_store_manager()
            
            if collection == "courses":
                results = manager.search_courses(query, k=limit)
            elif collection == "assignments":
                results = manager.search_assignments(query, k=limit)
            else:
                return {"error": f"Unknown collection: {collection}"}
            
            return {
                "query": query,
                "collection": collection,
                "results": results,
                "count": len(results)
            }
        except Exception as e:
            return {
                "error": str(e),
                "message": "Semantic search not available. Using exact matching instead."
            }
