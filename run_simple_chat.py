"""
Simple Chat Test - NO REDIS REQUIRED
=====================================
Run: python run_simple_chat.py

This is a minimal test that bypasses Redis.
Uses CrewAI directly with hardcoded student.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check for OpenAI API key
api_key = os.getenv("OPENAI_API_KEY", "")
if not api_key or api_key == "your-openai-api-key-here":
    print("=" * 60)
    print("❌ ERROR: OpenAI API key not set!")
    print("=" * 60)
    print("\nPlease add your OpenAI API key to .env file:")
    print("  OPENAI_API_KEY=sk-your-actual-key-here")
    print("\nGet your key from: https://platform.openai.com/api-keys")
    sys.exit(1)

# Set API key for CrewAI
os.environ["OPENAI_API_KEY"] = api_key

# Disable CrewAI telemetry and Redis usage
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

print("=" * 60)
print("🎓 IBA SUKKUR UNIVERSITY - SIMPLE CHAT TEST")
print("=" * 60)
print("\n🔄 Loading modules...")

from pymongo import MongoClient
from config import get_settings
from utils.agentops_setup import init_agentops

init_agentops()

from crewai import Agent, Task, Crew, Process

from agents.tools.database_tools import (
    StudentInfoTool,
    AssignmentQueryTool,
    FeeQueryTool,
    ExamQueryTool,
    GradeQueryTool,
)


def get_student_data():
    """Get Ali Khan's data from MongoDB."""
    settings = get_settings()
    client = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_database]
    
    student = db["students"].find_one({"roll_number": "CS-2023-001"})
    if not student:
        print("❌ Student not found! Run 'python dummy_db_generate.py' first.")
        sys.exit(1)
    
    return {
        "student_id": str(student["_id"]),
        "student_name": student.get("full_name"),
        "roll_number": student.get("roll_number"),
        "email": student.get("email"),
        "semester": student.get("semester"),
        "department": student.get("department"),
    }


def create_agent_for_intent(intent: str, student_context: dict):
    """Create a simple agent based on intent."""
    
    # Define agents for each intent
    agents_config = {
        "FEE": {
            "role": "Fee Status Specialist",
            "goal": "Help students check their fee status, payment history, and dues",
            "backstory": "You are a helpful fee advisor at IBA Sukkur University.",
            "tools": [FeeQueryTool(), StudentInfoTool()],
        },
        "ASSIGNMENT": {
            "role": "Assignment Specialist", 
            "goal": "Help students with assignment status, due dates, and submissions",
            "backstory": "You are an assignment tracker at IBA Sukkur University.",
            "tools": [AssignmentQueryTool(), StudentInfoTool()],
        },
        "EXAM": {
            "role": "Exam Schedule Specialist",
            "goal": "Help students with exam schedules, dates, and venues",
            "backstory": "You are an exam coordinator at IBA Sukkur University.",
            "tools": [ExamQueryTool(), StudentInfoTool()],
        },
        "GRADE": {
            "role": "Academic Records Specialist",
            "goal": "Help students check their grades, CGPA, and results",
            "backstory": "You are an academic advisor at IBA Sukkur University.",
            "tools": [GradeQueryTool(), StudentInfoTool()],
        },
    }
    
    config = agents_config.get(intent, agents_config["FEE"])
    
    return Agent(
        role=config["role"],
        goal=config["goal"],
        backstory=config["backstory"],
        tools=config["tools"],
        verbose=True,
    )


def classify_intent(query: str) -> str:
    """Simple keyword-based intent classification."""
    query_lower = query.lower()
    
    if any(word in query_lower for word in ["fee", "fees", "payment", "dues", "challan", "paid", "unpaid"]):
        return "FEE"
    elif any(word in query_lower for word in ["assignment", "homework", "submit", "due", "pending", "overdue"]):
        return "ASSIGNMENT"
    elif any(word in query_lower for word in ["exam", "paper", "schedule", "midterm", "final", "test"]):
        return "EXAM"
    elif any(word in query_lower for word in ["grade", "result", "marks", "cgpa", "gpa", "score"]):
        return "GRADE"
    else:
        return "FEE"  # Default


def process_query(query: str, student: dict) -> str:
    """Process a query using CrewAI."""
    
    # Classify intent
    intent = classify_intent(query)
    print(f"\n🔍 Detected intent: {intent}")
    
    # Create agent
    agent = create_agent_for_intent(intent, student)
    
    # Create task
    task = Task(
        description=f"""
        Student Query: "{query}"
        
        Student Information:
        - Name: {student['student_name']}
        - Roll Number: {student['roll_number']}
        - Student ID: {student['student_id']}
        - Semester: {student['semester']}
        - Department: {student['department']}
        
        Use the available tools to fetch the relevant information and provide a helpful, 
        friendly response in natural language. If the query is in Roman Urdu, respond in 
        a mix of English and Roman Urdu.
        """,
        expected_output="A helpful response answering the student's query with specific data.",
        agent=agent,
    )
    
    # Create and run crew
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    
    result = crew.kickoff()
    return str(result)


def main():
    """Main function."""
    
    # Load student data
    print("\n📋 Loading student data...")
    student = get_student_data()
    print(f"✅ Student: {student['student_name']} ({student['roll_number']})")
    print(f"   Semester: {student['semester']} | Department: {student['department']}")
    
    print("\n" + "=" * 60)
    print("💬 CHAT MODE")
    print("=" * 60)
    print("\n📝 Sample queries:")
    print("   • meri fees ka status batao")
    print("   • which assignments are pending?")
    print("   • exam kab hai?")
    print("   • mera result batao")
    print("\n💡 Type 'quit' to exit")
    print("─" * 60)
    
    while True:
        try:
            print()
            user_input = input("🧑 You: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ["quit", "exit", "bye", "q"]:
                print("\n👋 Goodbye!")
                break
            
            print("\n🤖 Processing...")
            print("─" * 40)
            
            start_time = datetime.now()
            response = process_query(user_input, student)
            end_time = datetime.now()
            
            processing_time = (end_time - start_time).total_seconds()
            
            print("─" * 40)
            print(f"\n🤖 Assistant: {response}")
            print(f"\n⏱️  ({processing_time:.1f}s)")
            print("─" * 60)
            
        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Please try again.")


def quick_test():
    """Run a quick test with one query."""
    print("\n📋 Loading student data...")
    student = get_student_data()
    print(f"✅ Student: {student['student_name']} ({student['roll_number']})")
    
    query = "meri fees ka status batao"
    print(f"\n📝 Test Query: \"{query}\"")
    print("─" * 60)
    
    response = process_query(query, student)
    
    print("─" * 60)
    print(f"\n✅ Response:\n{response}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run quick test")
    args = parser.parse_args()
    
    if args.test:
        quick_test()
    else:
        main()
