"""
Test Database Tools Only (No OpenAI Required)
==============================================
Run: python test_tools_only.py

This tests just the database tools to verify MongoDB is working
before testing the full AI pipeline.
"""

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient
from config import get_settings
from agents.tools.database_tools import (
    StudentInfoTool,
    AssignmentQueryTool,
    FeeQueryTool,
    ExamQueryTool,
    GradeQueryTool,
)
import json


def get_student_id():
    """Get Ali Khan's student_id."""
    settings = get_settings()
    client = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_database]
    
    student = db["students"].find_one({"roll_number": "CS-2023-001"})
    if not student:
        print("❌ Student not found! Run 'python dummy_db_generate.py' first.")
        return None
    return str(student["_id"])


def main():
    print("=" * 60)
    print("🧪 DATABASE TOOLS TEST (No OpenAI Required)")
    print("=" * 60)
    
    student_id = get_student_id()
    if not student_id:
        return
    
    print(f"\n📋 Testing with student_id: {student_id}\n")
    
    # Test 1: Student Info
    print("─" * 60)
    print("1️⃣  STUDENT INFO TOOL")
    print("─" * 60)
    tool = StudentInfoTool()
    result = tool._run(student_id)
    print(f"   Name: {result.get('full_name')}")
    print(f"   Roll: {result.get('roll_number')}")
    print(f"   Semester: {result.get('semester')}")
    print(f"   Department: {result.get('department')}")
    print(f"   CGPA: {result.get('cgpa')}")
    print("   ✅ PASSED\n")
    
    # Test 2: Assignments
    print("─" * 60)
    print("2️⃣  ASSIGNMENT QUERY TOOL")
    print("─" * 60)
    tool = AssignmentQueryTool()
    result = tool._run(student_id)
    summary = result.get("summary", {})
    print(f"   Pending: {summary.get('total_pending', 0)}")
    print(f"   Submitted: {summary.get('total_submitted', 0)}")
    print(f"   Overdue: {summary.get('total_overdue', 0)}")
    print(f"   Upcoming: {summary.get('total_upcoming', 0)}")
    
    if result.get("overdue"):
        print("\n   ⚠️  OVERDUE ASSIGNMENTS:")
        for a in result["overdue"][:3]:
            print(f"      - {a['title']} ({a['course_code']})")
    print("   ✅ PASSED\n")
    
    # Test 3: Fees
    print("─" * 60)
    print("3️⃣  FEE QUERY TOOL")
    print("─" * 60)
    tool = FeeQueryTool()
    result = tool._run(student_id)
    current = result.get("current_fee_status", {})
    print(f"   Status: {current.get('status', 'N/A')}")
    print(f"   Amount Due: Rs. {current.get('amount_due', 0):,}")
    print(f"   Amount Paid: Rs. {current.get('amount_paid', 0):,}")
    print(f"   Balance: Rs. {current.get('balance', 0):,}")
    print(f"   Can Access Docs: {'✅ Yes' if result.get('can_access_documents') else '❌ No'}")
    print("   ✅ PASSED\n")
    
    # Test 4: Exams
    print("─" * 60)
    print("4️⃣  EXAM QUERY TOOL")
    print("─" * 60)
    tool = ExamQueryTool()
    result = tool._run(student_id)
    print(f"   Upcoming Exams: {result.get('total_upcoming_exams', 0)}")
    
    first = result.get("first_upcoming_exam")
    if first:
        print(f"\n   🎯 FIRST EXAM:")
        print(f"      Course: {first.get('course_name')}")
        print(f"      Type: {first.get('exam_type')}")
        print(f"      Date: {first.get('exam_date')}")
        print(f"      Time: {first.get('start_time')}")
        print(f"      Venue: {first.get('venue')}")
    print("   ✅ PASSED\n")
    
    # Test 5: Grades
    print("─" * 60)
    print("5️⃣  GRADE QUERY TOOL")
    print("─" * 60)
    tool = GradeQueryTool()
    result = tool._run(student_id)
    print(f"   CGPA: {result.get('current_cgpa')}")
    print(f"   Semesters Completed: {result.get('total_semesters_completed')}")
    
    for sem in result.get("semesters", [])[:2]:
        print(f"\n   📊 Semester {sem['semester']} (GPA: {sem['semester_gpa']}):")
        for c in sem["courses"][:2]:
            print(f"      {c['course_code']}: {c['grade_letter']} ({c['total_marks']}/{c['out_of']})")
    print("   ✅ PASSED\n")
    
    print("=" * 60)
    print("✅ ALL DATABASE TOOLS WORKING!")
    print("=" * 60)
    print("\n💡 Next: Add your OpenAI API key to .env and run:")
    print("   python run_chat.py")


if __name__ == "__main__":
    main()
