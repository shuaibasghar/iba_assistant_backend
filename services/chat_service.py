"""
Chat Service - Main Integration Layer
======================================
Integrates LangChain (conversation) with CrewAI (orchestration).

Flow:
    User Message → LangChain Memory → Intent Detection → CrewAI Agent → Response
"""

import os
from typing import Optional
from datetime import datetime
from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

from config import get_settings
from .session_manager import SessionManager, StudentSession, get_session_manager
from .conversation_manager import ConversationManager, ConversationManagerFactory
from agents.university_crew import UniversityCrewFactory, _CREW_ROUTE_INTENTS
from utils.query_scope import detect_assignment_reply_scope, detect_grade_reply_scope
from utils.permissions import check_user_permission


@dataclass
class ChatResponse:
    """Response from chat service."""
    session_id: str
    message: str
    intent: str
    student_name: str
    timestamp: str
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "message": self.message,
            "intent": self.intent,
            "student_name": self.student_name,
            "timestamp": self.timestamp,
            "processing_time_ms": self.processing_time_ms,
        }


class IntentClassifier:
    """
    Lightweight intent classifier using LangChain.
    Faster than using full CrewAI for simple classification.
    """
    
    # Order: route intents first (same as crew router), GENERAL last.
    INTENTS = list(_CREW_ROUTE_INTENTS) + ["GENERAL"]
    
    def __init__(self):
        settings = get_settings()
        
        # Set API key
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
        )
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an intent classifier for a university portal (students and faculty).
Classify the user's query into ONE of these categories:
- ASSIGNMENT: Assignments, homework, submissions, due dates
- FEE: Fees, payment, dues, challan
- EXAM: Exams, schedule, papers, dates, venues, admit card, hall ticket
- GRADE: Grades, marks, results, CGPA, GPA
- DOCUMENT: Transcripts, enrollment certificates, official document status
- ATTENDANCE: Class attendance, shortage, percentage, 75% rule
- TIMETABLE: Class schedule, time table, room, which class when
- LIBRARY: Library books, due dates, fines, returns
- SCHOLARSHIP: Scholarships, financial aid, stipend, disbursement
- HOSTEL: Hostel room, warden, hostel fee, accommodation
- COMPLAINT: Complaints, support tickets, grievances
- ANNOUNCEMENT: Campus notices, circulars, news, alerts
- EMAIL: Sending an email, forwarding to an address, Gmail/mail requests
- GENERAL: Greetings, small talk, unclear intent

Respond with ONLY the category name, nothing else.

User is: {student_name} | Role: {user_role} | Semester: {semester} | Dept: {department}
Recent conversation:
{conversation_history}
"""),
            ("human", "{query}")
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def classify(
        self, 
        query: str, 
        student_context: dict,
        conversation_history: str = ""
    ) -> str:
        """Classify query intent."""
        try:
            result = self.chain.invoke({
                "query": query,
                "student_name": student_context.get("student_name", "Student"),
                "user_role": student_context.get("user_role", "student"),
                "semester": student_context.get("semester", "Unknown"),
                "department": student_context.get("department", "Unknown"),
                "conversation_history": conversation_history or "No previous conversation."
            })
            
            # Extract intent from response
            result = result.strip().upper()
            for intent in self.INTENTS:
                if intent in result:
                    return intent
            
            return "GENERAL"
        
        except Exception as e:
            print(f"Intent classification error: {e}")
            return "GENERAL"


class ChatService:
    """
    Main chat service that orchestrates everything.
    
    Usage:
        service = ChatService()
        
        # Start session (on login)
        session = service.start_session(roll_number="CS-2023-001")
        
        # Handle messages
        response = service.chat(session.session_id, "meri fees ka status batao")
        
        # End session (on logout)
        service.end_session(session.session_id)
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.session_manager = get_session_manager()
        self.intent_classifier = IntentClassifier()
        
        # Set OpenAI API key for CrewAI
        os.environ["OPENAI_API_KEY"] = self.settings.openai_api_key
    
    def start_session(
        self,
        student_id: str = None,
        roll_number: str = None,
        email: str = None,
        tenant_id: str = "default",
        hint_role: str | None = None,
    ) -> Optional[StudentSession]:
        """
        Start a new chat session. Pass hint_role matching JWT role (student | teacher | admin).
        """
        session = self.session_manager.create_session(
            student_id=student_id,
            roll_number=roll_number,
            email=email,
            tenant_id=tenant_id,
            hint_role=hint_role,
        )
        
        if session:
            # Initialize conversation manager for this session
            ConversationManagerFactory.get_manager(
                session_id=session.session_id,
                session=session
            )
        
        return session
    
    def get_session(self, session_id: str) -> Optional[StudentSession]:
        """Get existing session."""
        return self.session_manager.get_session(session_id)
    
    def end_session(self, session_id: str) -> bool:
        """End a session (logout)."""
        # Clean up conversation manager
        ConversationManagerFactory.remove_manager(session_id)
        
        # Delete session from Redis
        return self.session_manager.delete_session(session_id)
    
    def chat(self, session_id: str, message: str) -> ChatResponse:
        """
        Process a chat message.
        
        Flow:
        1. Validate session
        2. Get conversation context
        3. Classify intent (LangChain)
        4. Execute with CrewAI agent
        5. Save to conversation history
        6. Return response
        """
        start_time = datetime.now()
        
        # 1. Get session
        session = self.session_manager.get_session(session_id)
        if not session:
            return ChatResponse(
                session_id=session_id,
                message="Session expired. Please login again.",
                intent="ERROR",
                student_name="Unknown",
                timestamp=datetime.now().isoformat()
            )
        
        # Refresh session TTL
        self.session_manager.refresh_session(session_id)
        
        # 2. Get conversation manager and context
        conv_manager = ConversationManagerFactory.get_manager(
            session_id=session_id,
            session=session
        )
        conversation_history = conv_manager.get_conversation_context()
        student_context = session.get_context()

        # 2.5 Permission layer: deny sensitive requests immediately
        permission_denial = check_user_permission(message, student_context.get("user_role", "student"))
        if permission_denial:
            response_text = permission_denial
            intent = "DENIED"
            conv_manager.add_exchange(message, response_text)
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            return ChatResponse(
                session_id=session_id,
                message=response_text,
                intent=intent,
                student_name=session.student_name,
                timestamp=datetime.now().isoformat(),
                processing_time_ms=processing_time
            )

        # 3. Intent: role-specific crew (faculty/admin) vs classifier for students
        ur = student_context.get("user_role", "student")
        if ur == "teacher":
            intent = "TEACHER"
        elif ur == "admin":
            intent = "ADMIN"
        else:
            intent = self.intent_classifier.classify(
                query=message,
                student_context=student_context,
                conversation_history=conversation_history
            )

        # Narrow reply scope (assignments / grades) — injected into Crew task text so the model obeys it
        crew_context = dict(student_context)
        if intent == "ASSIGNMENT":
            crew_context["assignment_reply_scope"] = detect_assignment_reply_scope(message)
        elif intent == "GRADE":
            crew_context["grade_reply_scope"] = detect_grade_reply_scope(message)
        
        # 4. Execute with CrewAI
        try:
            response_text = self._execute_with_crewai(
                intent=intent,
                query=message,
                student_context=crew_context,
                conversation_history=conversation_history,
                tenant_id=session.tenant_id
            )
        except Exception as e:
            print(f"CrewAI error: {e}")
            response_text = f"I'm having trouble processing your request. Please try again. (Error: {str(e)[:100]})"
        
        # 5. Save to conversation history
        conv_manager.add_exchange(message, response_text)
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # 6. Return response
        return ChatResponse(
            session_id=session_id,
            message=response_text,
            intent=intent,
            student_name=session.student_name,
            timestamp=datetime.now().isoformat(),
            processing_time_ms=processing_time
        )
    
    def _execute_with_crewai(
        self,
        intent: str,
        query: str,
        student_context: dict,
        conversation_history: str,
        tenant_id: str
    ) -> str:
        """Execute query using CrewAI agents."""
        
        # Add conversation history to context
        context = {
            **student_context,
            "conversation_history": conversation_history
        }
        
        # Create specialist crew and execute
        factory = UniversityCrewFactory(tenant_id=tenant_id)
        crew = factory.create_specialist_crew(
            intent=intent,
            query=query,
            student_context=context
        )
        
        result = crew.kickoff()
        return str(result)
    
    def get_chat_history(self, session_id: str) -> list:
        """Get chat history for a session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            return []
        
        conv_manager = ConversationManagerFactory.get_manager(
            session_id=session_id,
            session=session
        )
        
        messages = conv_manager.get_chat_history()
        return [
            {
                "role": "user" if msg.type == "human" else "assistant",
                "content": msg.content
            }
            for msg in messages
        ]


# Singleton instance
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Get singleton ChatService instance."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
