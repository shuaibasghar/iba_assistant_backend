"""
Terminal Chat - IBA Sukkur University Portal
=============================================
Run: python run_chat.py

This script demonstrates the full chat flow with verbose output.
Uses hardcoded student (Ali Khan - CS-2023-001) for testing.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check for OpenAI API key
if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your-openai-api-key-here":
    print("=" * 60)
    print("❌ ERROR: OpenAI API key not set!")
    print("=" * 60)
    print("\nPlease add your OpenAI API key to .env file:")
    print("  OPENAI_API_KEY=sk-your-actual-key-here")
    print("\nGet your key from: https://platform.openai.com/api-keys")
    sys.exit(1)

print("=" * 60)
print("🎓 IBA SUKKUR UNIVERSITY PORTAL - TERMINAL CHAT")
print("=" * 60)
print("\n🔄 Loading modules...")

from config import get_settings
from pymongo import MongoClient
from services.session_manager import SessionManager
from services.conversation_manager import ConversationManagerFactory
from services.chat_service import ChatService, IntentClassifier
from agents.university_crew import UniversityCrewFactory

# Verbose flag
VERBOSE = True

def log(message: str, level: str = "INFO"):
    """Print verbose log messages."""
    if VERBOSE:
        timestamp = datetime.now().strftime("%H:%M:%S")
        icons = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "ERROR": "❌",
            "STEP": "➡️",
            "AGENT": "🤖",
            "DB": "🗄️",
            "CHAT": "💬",
        }
        icon = icons.get(level, "•")
        print(f"  [{timestamp}] {icon} {message}")


def get_hardcoded_student():
    """Get Ali Khan (CS-2023-001) for testing."""
    settings = get_settings()
    client = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_database]
    
    # Try to find Ali Khan
    student = db["students"].find_one({"roll_number": "CS-2023-001"})
    
    if not student:
        print("\n❌ Student not found! Run 'python dummy_db_generate.py' first.")
        sys.exit(1)
    
    return {
        "student_id": str(student["_id"]),
        "student_name": student.get("full_name"),
        "roll_number": student.get("roll_number"),
        "email": student.get("email"),
        "semester": student.get("semester"),
        "department": student.get("department"),
        "batch": student.get("batch"),
        "cgpa": student.get("cgpa"),
    }


def run_terminal_chat():
    """Main terminal chat loop."""
    
    print("\n" + "─" * 60)
    print("📋 STEP 1: Loading Student Data")
    print("─" * 60)
    
    student = get_hardcoded_student()
    log(f"Student loaded: {student['student_name']}", "SUCCESS")
    log(f"Roll Number: {student['roll_number']}", "INFO")
    log(f"Email: {student['email']}", "INFO")
    log(f"Semester: {student['semester']} | Department: {student['department']}", "INFO")
    log(f"CGPA: {student['cgpa']}", "INFO")
    
    print("\n" + "─" * 60)
    print("🔧 STEP 2: Initializing Services")
    print("─" * 60)
    
    log("Initializing Intent Classifier (LangChain + OpenAI)...", "STEP")
    intent_classifier = IntentClassifier()
    log("Intent Classifier ready", "SUCCESS")
    
    log("Initializing CrewAI Factory...", "STEP")
    crew_factory = UniversityCrewFactory(tenant_id="iba_sukkur")
    log("CrewAI Factory ready", "SUCCESS")
    
    # Conversation history (in-memory for this demo)
    conversation_history = []
    
    print("\n" + "=" * 60)
    print(f"🎉 Welcome, {student['student_name']}!")
    print("=" * 60)
    print("\n📝 You can ask questions like:")
    print("   • meri fees ka status batao")
    print("   • which assignments are pending?")
    print("   • exam kab hai?")
    print("   • mera result batao")
    print("   • transcript chahiye")
    print("\n💡 Type 'quit' or 'exit' to end the session")
    print("─" * 60)
    
    while True:
        try:
            # Get user input
            print()
            user_input = input("🧑 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ["quit", "exit", "bye", "q"]:
                print("\n👋 Goodbye! Session ended.")
                break
            
            # Process the message
            print("\n" + "─" * 40)
            log("Processing your query...", "CHAT")
            
            # Step 1: Classify intent
            log("STEP: Classifying intent with LangChain...", "STEP")
            
            # Build conversation context
            conv_context = "\n".join([
                f"{'Student' if i % 2 == 0 else 'Assistant'}: {msg}"
                for i, msg in enumerate(conversation_history[-6:])
            ]) if conversation_history else "No previous conversation."
            
            intent = intent_classifier.classify(
                query=user_input,
                student_context=student,
                conversation_history=conv_context
            )
            log(f"Intent detected: {intent}", "SUCCESS")
            
            # Step 2: Execute with CrewAI
            log(f"STEP: Creating {intent} specialist agent...", "AGENT")
            
            context_with_history = {
                **student,
                "conversation_history": conv_context
            }
            
            log("STEP: Building CrewAI crew...", "AGENT")
            crew = crew_factory.create_specialist_crew(
                intent=intent,
                query=user_input,
                student_context=context_with_history
            )
            
            log("STEP: Executing crew (this may take a moment)...", "AGENT")
            print("─" * 40)
            print("\n🤖 Agent Working...\n")
            
            # Execute crew
            start_time = datetime.now()
            result = crew.kickoff()
            end_time = datetime.now()
            
            processing_time = (end_time - start_time).total_seconds()
            
            response = str(result)
            
            print("─" * 40)
            log(f"Response generated in {processing_time:.2f}s", "SUCCESS")
            
            # Save to history
            conversation_history.append(user_input)
            conversation_history.append(response)
            
            # Display response
            print(f"\n🤖 Assistant ({intent}):")
            print("─" * 40)
            print(response)
            print("─" * 40)
            
        except KeyboardInterrupt:
            print("\n\n👋 Session interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            log(f"Error details: {type(e).__name__}: {e}", "ERROR")
            print("Please try again with a different question.")


def run_simple_test():
    """Run a quick test with predefined questions."""
    print("\n" + "=" * 60)
    print("🧪 QUICK TEST MODE")
    print("=" * 60)
    
    student = get_hardcoded_student()
    print(f"\n👤 Testing as: {student['student_name']} ({student['roll_number']})")
    
    intent_classifier = IntentClassifier()
    crew_factory = UniversityCrewFactory(tenant_id="iba_sukkur")
    
    test_queries = [
        "meri fees ka status batao",
        # "which assignments are pending?",
        # "exam kab hai pehla paper?",
    ]
    
    for query in test_queries:
        print("\n" + "=" * 60)
        print(f"📝 Query: \"{query}\"")
        print("=" * 60)
        
        # Classify
        print("\n🔍 Classifying intent...")
        intent = intent_classifier.classify(query, student)
        print(f"   Intent: {intent}")
        
        # Execute
        print(f"\n🤖 Executing {intent} agent...")
        crew = crew_factory.create_specialist_crew(
            intent=intent,
            query=query,
            student_context=student
        )
        
        result = crew.kickoff()
        
        print(f"\n💬 Response:")
        print("─" * 40)
        print(str(result))
        print("─" * 40)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="IBA Sukkur University Portal - Terminal Chat")
    parser.add_argument("--test", action="store_true", help="Run quick test with predefined queries")
    parser.add_argument("--quiet", action="store_true", help="Disable verbose output")
    
    args = parser.parse_args()
    
    if args.quiet:
        VERBOSE = False
    
    if args.test:
        run_simple_test()
    else:
        run_terminal_chat()
