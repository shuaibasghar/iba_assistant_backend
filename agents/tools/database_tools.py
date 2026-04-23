"""
Database Query Tools for CrewAI Agents
These tools allow agents to query the MongoDB database.
"""

from crewai.tools import BaseTool
from typing import Type, Any
from pydantic import BaseModel, Field
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from config import get_settings


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
    Get basic information about a student including name, roll number, 
    semester, department, and CGPA. Use this to get student context.
    """
    args_schema: Type[BaseModel] = StudentIdInput

    def _run(self, student_id: str) -> dict:
        db = get_db()
        student = find_student(db, student_id)
        
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        
        return {
            "student_id": str(student["_id"]),
            "full_name": student.get("full_name"),
            "roll_number": student.get("roll_number"),
            "email": student.get("email"),
            "semester": student.get("semester"),
            "department": student.get("department"),
            "batch": student.get("batch"),
            "cgpa": student.get("cgpa"),
            "status": student.get("status"),
        }


# ═══════════════════════════════════════════════════════════════════
# Assignment Query Tool
# ═══════════════════════════════════════════════════════════════════

class AssignmentQueryTool(BaseTool):
    name: str = "query_assignments"
    description: str = """
    Query assignments for a student. Returns pending, submitted, and overdue 
    assignments with due dates and marks. Can filter by semester.
    """
    args_schema: Type[BaseModel] = StudentSemesterInput

    def _run(self, student_id: str, semester: int | None = None) -> dict:
        db = get_db()
        
        # Get student's enrolled courses
        student = find_student(db, student_id)
        if not student:
            return {"error": f"Student not found with identifier: {student_id}"}
        
        student_oid = student["_id"]
        current_semester = semester or student.get("semester")
        
        # Get courses for this semester
        courses = list(db["courses"].find({"semester": current_semester}))
        course_ids = [c["_id"] for c in courses]
        course_map = {str(c["_id"]): c for c in courses}
        
        # Get assignments for these courses
        assignments = list(db["assignments"].find({"course_id": {"$in": course_ids}}))
        
        # Get submissions for this student
        assignment_ids = [a["_id"] for a in assignments]
        submissions = list(db["assignment_submissions"].find({
            "student_id": student_oid,
            "assignment_id": {"$in": assignment_ids}
        }))
        submission_map = {str(s["assignment_id"]): s for s in submissions}
        
        now = datetime.now()
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
            
            assignment_info = {
                "title": a.get("title"),
                "course_name": course.get("course_name"),
                "course_code": a.get("course_code"),
                "due_date": a.get("due_date").strftime("%Y-%m-%d %H:%M") if a.get("due_date") else None,
                "total_marks": a.get("total_marks"),
            }
            
            if sub:
                assignment_info["status"] = sub.get("status")
                assignment_info["marks_obtained"] = sub.get("marks_obtained")
                assignment_info["submitted_at"] = sub.get("submitted_at").strftime("%Y-%m-%d") if sub.get("submitted_at") else None
                assignment_info["feedback"] = sub.get("feedback")
                
                if sub.get("status") == "submitted":
                    result["submitted"].append(assignment_info)
                elif sub.get("status") == "overdue":
                    result["overdue"].append(assignment_info)
                else:
                    if a.get("due_date") and a.get("due_date") > now:
                        result["pending"].append(assignment_info)
                    else:
                        result["overdue"].append(assignment_info)
            else:
                if a.get("due_date") and a.get("due_date") > now:
                    days_left = (a.get("due_date") - now).days
                    assignment_info["days_until_due"] = days_left
                    if days_left > 7:
                        result["upcoming"].append(assignment_info)
                    else:
                        result["pending"].append(assignment_info)
                else:
                    result["overdue"].append(assignment_info)
        
        result["summary"] = {
            "total_pending": len(result["pending"]),
            "total_submitted": len(result["submitted"]),
            "total_overdue": len(result["overdue"]),
            "total_upcoming": len(result["upcoming"]),
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
        now = datetime.now()
        
        # Get exams for this semester
        exams = list(db["exams"].find({
            "semester": current_semester,
            "exam_date": {"$gte": now}
        }).sort("exam_date", 1))
        
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
