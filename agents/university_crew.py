"""
IBA Sukkur University Portal - Scalable Multi-Agent System
===========================================================
Dynamic agent creation optimized for SaaS multi-tenant architecture.

Architecture:
    Request → Router (lightweight) → Detect Intent → Create Specialist → Execute → Cleanup

Benefits:
    - Only loads agents needed per request
    - Memory efficient for concurrent users
    - Multi-tenant ready (different DB configs per university)
    - Easy to add new agents without code changes
"""

from crewai import Agent, Task, Crew, Process
from pathlib import Path
from typing import Any
import yaml

from .tools.database_tools import (
    AdmitCardQueryTool,
    AnnouncementQueryTool,
    AssignmentQueryTool,
    AttendanceQueryTool,
    ComplaintQueryTool,
    CourseTeacherQueryTool,
    FeeQueryTool,
    ExamQueryTool,
    GradeQueryTool,
    HostelQueryTool,
    LibraryQueryTool,
    RecordsQueryTool,
    ScholarshipQueryTool,
    StudentInfoTool,
    TeacherTeachingQueryTool,
    TimetableQueryTool,
)
from utils.query_scope import assignment_scope_prompt, grade_scope_prompt
from .tools.platform_email_tools import get_platform_email_tools

# Match order used for substring routing (exclude GENERAL).
_CREW_ROUTE_INTENTS = (
    "SCHOLARSHIP",
    "ANNOUNCEMENT",
    "ATTENDANCE",
    "TIMETABLE",
    "COMPLAINT",
    "LIBRARY",
    "HOSTEL",
    "DOCUMENT",
    "ASSIGNMENT",
    "FEE",
    "EXAM",
    "GRADE",
    "EMAIL",
)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION LOADER
# ═══════════════════════════════════════════════════════════════════════════════

class AgentConfigLoader:
    """
    Loads agent and task configurations from YAML files.
    Can be extended to load from database for multi-tenant support.
    """
    
    _config_cache: dict = {}
    
    @classmethod
    def get_config_path(cls) -> Path:
        return Path(__file__).parent / "config"
    
    @classmethod
    def load_agents_config(cls, tenant_id: str = "default") -> dict:
        """Load agents config. Can be extended to load tenant-specific configs."""
        cache_key = f"agents_{tenant_id}"
        
        if cache_key not in cls._config_cache:
            config_path = cls.get_config_path() / "agents.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                cls._config_cache[cache_key] = yaml.safe_load(f)
        
        return cls._config_cache[cache_key]
    
    @classmethod
    def load_tasks_config(cls, tenant_id: str = "default") -> dict:
        """Load tasks config. Can be extended to load tenant-specific configs."""
        cache_key = f"tasks_{tenant_id}"
        
        if cache_key not in cls._config_cache:
            config_path = cls.get_config_path() / "tasks.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                cls._config_cache[cache_key] = yaml.safe_load(f)
        
        return cls._config_cache[cache_key]
    
    @classmethod
    def clear_cache(cls):
        """Clear config cache (useful when configs are updated)."""
        cls._config_cache.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

class ToolFactory:
    """
    Creates tools on-demand. Each request gets fresh tool instances.
    Can be extended to inject tenant-specific database connections.
    """
    
    @staticmethod
    def create_tool(tool_name: str, db_config: dict = None) -> Any:
        """Create a tool instance by name."""
        tools = {
            "student_info": StudentInfoTool,
            "assignment": AssignmentQueryTool,
            "fee": FeeQueryTool,
            "exam": ExamQueryTool,
            "admit_card": AdmitCardQueryTool,
            "grade": GradeQueryTool,
            "records": RecordsQueryTool,
            "attendance": AttendanceQueryTool,
            "timetable": TimetableQueryTool,
            "course_teacher": CourseTeacherQueryTool,
            "library": LibraryQueryTool,
            "scholarship": ScholarshipQueryTool,
            "hostel": HostelQueryTool,
            "complaint": ComplaintQueryTool,
            "announcement": AnnouncementQueryTool,
            "teacher_teaching": TeacherTeachingQueryTool,
        }
        
        if tool_name not in tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        # Future: pass db_config for multi-tenant database connections
        return tools[tool_name]()
    
    @staticmethod
    def get_tools_for_intent(intent: str, db_config: dict = None) -> list:
        """Get the appropriate tools for a given intent."""
        if intent == "EMAIL":
            tools = list(get_platform_email_tools())
            tools.append(ToolFactory.create_tool("student_info", db_config))
            return tools

        if intent == "TEACHER":
            return [
                ToolFactory.create_tool("teacher_teaching", db_config),
                ToolFactory.create_tool("student_info", db_config),
                ToolFactory.create_tool("announcement", db_config),
            ]

        if intent == "ADMIN":
            return [
                ToolFactory.create_tool("student_info", db_config),
                ToolFactory.create_tool("announcement", db_config),
            ]

        intent_tools = {
            "ASSIGNMENT": ["assignment", "student_info"],
            "FEE": ["fee", "student_info"],
            "EXAM": ["exam", "admit_card", "student_info"],
            "GRADE": ["grade", "student_info"],
            "DOCUMENT": ["records", "fee", "student_info"],
            "ATTENDANCE": ["attendance", "student_info"],
            "TIMETABLE": ["timetable", "course_teacher", "student_info"],
            "LIBRARY": ["library", "student_info"],
            "SCHOLARSHIP": ["scholarship", "student_info"],
            "HOSTEL": ["hostel", "student_info"],
            "COMPLAINT": ["complaint", "student_info"],
            "ANNOUNCEMENT": ["announcement", "student_info"],
            "GENERAL": ["student_info"],
        }
        
        tool_names = intent_tools.get(intent, ["student_info"])
        return [ToolFactory.create_tool(name, db_config) for name in tool_names]


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

class AgentFactory:
    """
    Creates agents on-demand based on intent.
    Lightweight - only creates what's needed per request.
    """
    
    # Maps intent to agent config key
    INTENT_TO_AGENT = {
        "ASSIGNMENT": "assignment_agent",
        "FEE": "fee_agent",
        "EXAM": "exam_agent",
        "GRADE": "grade_agent",
        "DOCUMENT": "document_agent",
        "ATTENDANCE": "attendance_agent",
        "TIMETABLE": "timetable_agent",
        "LIBRARY": "library_agent",
        "SCHOLARSHIP": "scholarship_agent",
        "HOSTEL": "hostel_agent",
        "COMPLAINT": "complaint_agent",
        "ANNOUNCEMENT": "announcement_agent",
        "EMAIL": "email_agent",
        "TEACHER": "teacher_portal_agent",
        "ADMIN": "admin_portal_agent",
        "GENERAL": "general_assistant",
    }
    
    # Maps intent to task config key
    INTENT_TO_TASK = {
        "ASSIGNMENT": "fetch_assignments_task",
        "FEE": "check_fee_status_task",
        "EXAM": "get_exam_schedule_task",
        "GRADE": "fetch_grades_task",
        "DOCUMENT": "process_document_request_task",
        "ATTENDANCE": "fetch_attendance_task",
        "TIMETABLE": "fetch_timetable_task",
        "LIBRARY": "fetch_library_task",
        "SCHOLARSHIP": "fetch_scholarship_task",
        "HOSTEL": "fetch_hostel_task",
        "COMPLAINT": "fetch_complaints_task",
        "ANNOUNCEMENT": "fetch_announcements_task",
        "EMAIL": "send_email_task",
        "TEACHER": "teacher_portal_task",
        "ADMIN": "admin_portal_task",
        "GENERAL": "general_conversation_task",
    }
    
    @classmethod
    def create_router_agent(cls, tenant_id: str = "default") -> Agent:
        """Create a lightweight router agent for intent detection."""
        config = AgentConfigLoader.load_agents_config(tenant_id)
        agent_config = config["router_agent"]
        
        return Agent(
            role=agent_config["role"].strip(),
            goal=agent_config["goal"].strip(),
            backstory=agent_config["backstory"].strip(),
            tools=[ToolFactory.create_tool("student_info")],
            verbose=True,
            allow_delegation=False,  # Router doesn't delegate, just classifies
        )
    
    @classmethod
    def create_specialist_agent(
        cls, 
        intent: str, 
        tenant_id: str = "default",
        db_config: dict = None
    ) -> Agent:
        """Create a specialist agent based on detected intent."""
        config = AgentConfigLoader.load_agents_config(tenant_id)
        agent_key = cls.INTENT_TO_AGENT.get(intent, "general_assistant")
        agent_config = config[agent_key]
        
        tools = ToolFactory.get_tools_for_intent(intent, db_config)
        
        return Agent(
            role=agent_config["role"].strip(),
            goal=agent_config["goal"].strip(),
            backstory=agent_config["backstory"].strip(),
            tools=tools,
            verbose=True,
            allow_delegation=agent_config.get("allow_delegation", False),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TASK FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

class TaskFactory:
    """Creates tasks with dynamic context injection."""
    
    @classmethod
    def create_routing_task(
        cls,
        query: str,
        student_context: dict,
        agent: Agent,
        tenant_id: str = "default"
    ) -> Task:
        """Create a routing task to classify student intent."""
        config = AgentConfigLoader.load_tasks_config(tenant_id)
        task_config = config["route_query_task"]
        
        # Inject dynamic context into description
        description = task_config["description"].format(
            query=query,
            student_name=student_context.get("student_name", "Unknown"),
            roll_number=student_context.get("roll_number", "Unknown"),
            semester=student_context.get("semester", "Unknown"),
            department=student_context.get("department", "Unknown"),
        )
        
        return Task(
            description=description,
            expected_output=task_config["expected_output"],
            agent=agent,
        )
    
    @classmethod
    def create_specialist_task(
        cls,
        intent: str,
        query: str,
        student_context: dict,
        agent: Agent,
        tenant_id: str = "default"
    ) -> Task:
        """Create a specialist task for the detected intent."""
        config = AgentConfigLoader.load_tasks_config(tenant_id)
        task_key = AgentFactory.INTENT_TO_TASK.get(intent, "general_conversation_task")
        task_config = config[task_key]
        
        # Inject dynamic context into description
        format_args = dict(
            query=query,
            student_name=student_context.get("student_name", "Unknown"),
            student_id=student_context.get("student_id", ""),
            roll_number=student_context.get("roll_number", "Unknown"),
            semester=student_context.get("semester", "Unknown"),
            department=student_context.get("department", "Unknown"),
        )
        if task_key in (
            "general_conversation_task",
            "teacher_portal_task",
            "admin_portal_task",
        ):
            format_args["conversation_history"] = student_context.get(
                "conversation_history", "No previous messages."
            )
        if task_key == "fetch_assignments_task":
            scope = student_context.get("assignment_reply_scope", "ALL")
            format_args["assignment_reply_scope"] = assignment_scope_prompt(scope)
        if task_key == "fetch_grades_task":
            scope = student_context.get("grade_reply_scope", "ALL")
            format_args["grade_reply_scope"] = grade_scope_prompt(scope)
        description = task_config["description"].format(**format_args)
        
        return Task(
            description=description,
            expected_output=task_config["expected_output"],
            agent=agent,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CREW FACTORY - Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

class UniversityCrewFactory:
    """
    Main factory for creating crews on-demand.
    
    Usage:
        factory = UniversityCrewFactory(tenant_id="iba_sukkur")
        
        # Step 1: Route the query
        intent = factory.route_query(query, student_context)
        
        # Step 2: Execute with specialist
        result = factory.execute_query(intent, query, student_context)
    """
    
    def __init__(self, tenant_id: str = "default", db_config: dict = None):
        self.tenant_id = tenant_id
        self.db_config = db_config  # For multi-tenant DB connections
    
    def create_routing_crew(
        self, 
        query: str, 
        student_context: dict
    ) -> Crew:
        """
        Create a lightweight crew just for intent routing.
        Fast and memory efficient.
        """
        router = AgentFactory.create_router_agent(self.tenant_id)
        routing_task = TaskFactory.create_routing_task(
            query=query,
            student_context=student_context,
            agent=router,
            tenant_id=self.tenant_id
        )
        
        return Crew(
            agents=[router],
            tasks=[routing_task],
            process=Process.sequential,
            verbose=True,
        )
    
    def create_specialist_crew(
        self,
        intent: str,
        query: str,
        student_context: dict
    ) -> Crew:
        """
        Create a specialist crew based on detected intent.
        Only loads the agent needed for this specific query.
        """
        specialist = AgentFactory.create_specialist_agent(
            intent=intent,
            tenant_id=self.tenant_id,
            db_config=self.db_config
        )
        
        specialist_task = TaskFactory.create_specialist_task(
            intent=intent,
            query=query,
            student_context=student_context,
            agent=specialist,
            tenant_id=self.tenant_id
        )
        
        return Crew(
            agents=[specialist],
            tasks=[specialist_task],
            process=Process.sequential,
            verbose=True,
        )
    
    def route_query(self, query: str, student_context: dict) -> str:
        """
        Route a query to determine intent.
        Returns: Intent string (one of _CREW_ROUTE_INTENTS or GENERAL)
        """
        crew = self.create_routing_crew(query, student_context)
        result = crew.kickoff()
        
        # Parse intent from result (simplified - enhance as needed)
        result_text = str(result).upper()
        
        for intent in _CREW_ROUTE_INTENTS:
            if intent in result_text:
                return intent

        return "GENERAL"
    
    def execute_query(
        self, 
        intent: str, 
        query: str, 
        student_context: dict
    ) -> str:
        """
        Execute a query with the appropriate specialist agent.
        Returns: Natural language response for the student.
        """
        crew = self.create_specialist_crew(intent, query, student_context)
        result = crew.kickoff()
        return str(result)
    
    def handle_student_query(self, query: str, student_context: dict) -> dict:
        """
        Full pipeline: Route → Execute → Return result.
        
        This is the main entry point for handling student queries.
        
        Args:
            query: The student's question (can be English or Roman Urdu)
            student_context: Dict with student_id, student_name, roll_number, etc.
        
        Returns:
            Dict with intent, response, and metadata
        """
        # Step 1: Route to determine intent
        intent = self.route_query(query, student_context)
        
        # Step 2: Execute with appropriate specialist
        response = self.execute_query(intent, query, student_context)
        
        return {
            "intent": intent,
            "response": response,
            "student_id": student_context.get("student_id"),
            "query": query,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def process_student_query(
    query: str,
    student_context: dict,
    tenant_id: str = "default"
) -> dict:
    """
    Simple function to process a student query.
    
    Example:
        result = process_student_query(
            query="meri fees ka status batao",
            student_context={
                "student_id": "...",
                "student_name": "Ali Khan",
                "roll_number": "CS-2023-001",
                "semester": 3,
                "department": "CS"
            }
        )
        print(result["response"])
    """
    factory = UniversityCrewFactory(tenant_id=tenant_id)
    return factory.handle_student_query(query, student_context)


def quick_route(query: str) -> str:
    """
    Quickly classify a query intent without full execution.
    Useful for testing or pre-filtering.
    """
    factory = UniversityCrewFactory()
    dummy_context = {
        "student_name": "Test Student",
        "roll_number": "TEST-001",
        "semester": 1,
        "department": "CS"
    }
    return factory.route_query(query, dummy_context)
