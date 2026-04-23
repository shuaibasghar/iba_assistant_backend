"""
Test script for IBA Sukkur University Agents
Run: python test_agents.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from agents.tools.database_tools import (
    AssignmentQueryTool,
    FeeQueryTool,
    ExamQueryTool,
    GradeQueryTool,
    StudentInfoTool,
)
from agents.university_crew import (
    UniversityCrewFactory,
    AgentFactory,
    ToolFactory,
    AgentConfigLoader,
)
from pymongo import MongoClient
from config import get_settings


def get_test_student():
    """Get student data for testing (Ali - has unpaid fees)."""
    settings = get_settings()
    client = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_database]
    
    student = db["students"].find_one({"roll_number": "CS-2023-001"})
    if student:
        return {
            "student_id": str(student["_id"]),
            "student_name": student.get("full_name"),
            "roll_number": student.get("roll_number"),
            "semester": student.get("semester"),
            "department": student.get("department"),
            "email": student.get("email"),
        }
    return None


def test_tools():
    """Test all database tools."""
    student = get_test_student()
    
    if not student:
        print("❌ No test student found. Run dummy_db_generate.py first.")
        return
    
    student_id = student["student_id"]
    
    print("=" * 60)
    print("🧪 TESTING DATABASE TOOLS")
    print("=" * 60)
    
    # Test Student Info Tool
    print("\n📋 Testing StudentInfoTool...")
    print("-" * 40)
    tool = StudentInfoTool()
    result = tool._run(student_id)
    print(f"Student: {result.get('full_name')}")
    print(f"Roll Number: {result.get('roll_number')}")
    print(f"Semester: {result.get('semester')}")
    print(f"Department: {result.get('department')}")
    print(f"CGPA: {result.get('cgpa')}")
    
    # Test Assignment Tool
    print("\n📝 Testing AssignmentQueryTool...")
    print("-" * 40)
    tool = AssignmentQueryTool()
    result = tool._run(student_id)
    print(f"Pending: {result['summary']['total_pending']}")
    print(f"Submitted: {result['summary']['total_submitted']}")
    print(f"Overdue: {result['summary']['total_overdue']}")
    print(f"Upcoming: {result['summary']['total_upcoming']}")
    
    if result["overdue"]:
        print("\n⚠️  Overdue Assignments:")
        for a in result["overdue"][:3]:
            print(f"   - {a['title']} ({a['course_code']})")
    
    # Test Fee Tool
    print("\n💰 Testing FeeQueryTool...")
    print("-" * 40)
    tool = FeeQueryTool()
    result = tool._run(student_id)
    current = result.get("current_fee_status", {})
    print(f"Current Semester Status: {current.get('status', 'N/A')}")
    print(f"Amount Due: Rs. {current.get('amount_due', 0):,}")
    print(f"Amount Paid: Rs. {current.get('amount_paid', 0):,}")
    print(f"Balance: Rs. {current.get('balance', 0):,}")
    print(f"Can Access Documents: {'✅ Yes' if result.get('can_access_documents') else '❌ No'}")
    
    # Test Exam Tool
    print("\n📅 Testing ExamQueryTool...")
    print("-" * 40)
    tool = ExamQueryTool()
    result = tool._run(student_id)
    print(f"Total Upcoming Exams: {result.get('total_upcoming_exams', 0)}")
    
    first_exam = result.get("first_upcoming_exam")
    if first_exam:
        print(f"\n🎯 First Exam:")
        print(f"   Course: {first_exam.get('course_name')}")
        print(f"   Type: {first_exam.get('exam_type')}")
        print(f"   Date: {first_exam.get('exam_date')}")
        print(f"   Time: {first_exam.get('start_time')}")
        print(f"   Venue: {first_exam.get('venue')}")
    
    # Test Grade Tool
    print("\n📊 Testing GradeQueryTool...")
    print("-" * 40)
    tool = GradeQueryTool()
    result = tool._run(student_id)
    print(f"CGPA: {result.get('current_cgpa')}")
    print(f"Semesters Completed: {result.get('total_semesters_completed')}")
    
    for sem in result.get("semesters", []):
        print(f"\n   Semester {sem['semester']} (GPA: {sem['semester_gpa']}):")
        for course in sem["courses"][:2]:
            print(f"      {course['course_code']}: {course['grade_letter']} ({course['total_marks']}/{course['out_of']})")
    
    print("\n" + "=" * 60)
    print("✅ ALL DATABASE TOOLS TESTED SUCCESSFULLY")
    print("=" * 60)


def test_factories():
    """Test the scalable factory architecture."""
    print("\n" + "=" * 60)
    print("🏭 TESTING SCALABLE FACTORY ARCHITECTURE")
    print("=" * 60)
    
    # Test Config Loader
    print("\n📄 Testing AgentConfigLoader...")
    print("-" * 40)
    agents_config = AgentConfigLoader.load_agents_config()
    tasks_config = AgentConfigLoader.load_tasks_config()
    print(f"Agents loaded: {list(agents_config.keys())}")
    print(f"Tasks loaded: {list(tasks_config.keys())}")
    
    # Test Tool Factory
    print("\n🔧 Testing ToolFactory...")
    print("-" * 40)
    for intent in ["ASSIGNMENT", "FEE", "EXAM", "GRADE", "DOCUMENT"]:
        tools = ToolFactory.get_tools_for_intent(intent)
        tool_names = [t.__class__.__name__ for t in tools]
        print(f"   {intent:10} → {tool_names}")
    
    # Test Agent Factory
    print("\n🤖 Testing AgentFactory...")
    print("-" * 40)
    router = AgentFactory.create_router_agent()
    print(f"Router Agent: {router.role[:50]}...")
    
    for intent in ["ASSIGNMENT", "FEE", "EXAM"]:
        agent = AgentFactory.create_specialist_agent(intent)
        print(f"{intent} Agent: {agent.role[:40]}...")
    
    print("\n" + "=" * 60)
    print("✅ FACTORY ARCHITECTURE TESTED SUCCESSFULLY")
    print("=" * 60)


def test_crew_factory():
    """Test the UniversityCrewFactory."""
    student = get_test_student()
    
    if not student:
        print("❌ No test student found. Run dummy_db_generate.py first.")
        return
    
    print("\n" + "=" * 60)
    print("🎓 TESTING UNIVERSITY CREW FACTORY")
    print("=" * 60)
    
    factory = UniversityCrewFactory(tenant_id="iba_sukkur")
    
    print(f"\nStudent: {student['student_name']} ({student['roll_number']})")
    print(f"Semester: {student['semester']} | Department: {student['department']}")
    
    # Test crew creation (without executing - needs LLM)
    print("\n🔄 Testing Crew Creation...")
    print("-" * 40)
    
    test_query = "meri fees ka status batao"
    routing_crew = factory.create_routing_crew(test_query, student)
    print(f"Routing Crew created with {len(routing_crew.agents)} agent(s)")
    
    specialist_crew = factory.create_specialist_crew("FEE", test_query, student)
    print(f"Specialist Crew (FEE) created with {len(specialist_crew.agents)} agent(s)")
    
    print("\n" + "=" * 60)
    print("✅ CREW FACTORY TESTED SUCCESSFULLY")
    print("=" * 60)
    print("\n💡 To test full execution, add OPENAI_API_KEY to .env")


def test_sample_queries():
    """Show sample queries and their expected routing."""
    print("\n" + "=" * 60)
    print("🗣️  SAMPLE QUERIES & EXPECTED ROUTING")
    print("=" * 60)
    
    queries = [
        ("ASSIGNMENT", "mera koi assignment pending hai?"),
        ("ASSIGNMENT", "which assignments are overdue?"),
        ("ASSIGNMENT", "NLP ka assignment kab submit karna hai?"),
        ("FEE", "meri fees ka status batao"),
        ("FEE", "kya meri fees paid hai?"),
        ("FEE", "kitni fees baki hai?"),
        ("EXAM", "mere exams kab hain?"),
        ("EXAM", "pehla paper konsa hai?"),
        ("EXAM", "CS301 ka exam kis date ko hai?"),
        ("GRADE", "mera result batao 2nd semester ka"),
        ("GRADE", "meri CGPA kya hai?"),
        ("GRADE", "Database Systems mein kitne marks aaye?"),
        ("DOCUMENT", "mujhe transcript chahiye"),
        ("DOCUMENT", "enrollment certificate de do"),
    ]
    
    print("\n┌────────────┬─────────────────────────────────────────────┐")
    print("│ Intent     │ Query                                       │")
    print("├────────────┼─────────────────────────────────────────────┤")
    for intent, query in queries:
        print(f"│ {intent:10} │ {query:43} │")
    print("└────────────┴─────────────────────────────────────────────┘")


if __name__ == "__main__":
    print("\n" + "🚀" * 30 + "\n")
    print("   IBA SUKKUR UNIVERSITY - AGENT SYSTEM TEST")
    print("\n" + "🚀" * 30)
    
    test_tools()
    test_factories()
    test_crew_factory()
    test_sample_queries()
