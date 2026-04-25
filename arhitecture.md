# IBA Sukkur University Portal — Full System Architecture

> **Last updated:** 2026-04-24  
> A complete breakdown of every component, execution flow, and function chain in the system.

---

## 1. High-Level Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 14)                            │
│  App Router: /login → /chat → /dashboard → /settings                   │
│  Auth Context ← localStorage (JWT tokens)                              │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ HTTP REST (Bearer <token>)
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI + Uvicorn)                       │
│  Entry point: main.py → uvicorn.run("main:app", port=8000)             │
│                                                                          │
│  Routers:  /auth/*  ·  /chat/*  ·  /report/*  ·  /assignments/*        │
│                                                                          │
│  Services: AuthService · ChatService · SessionManager                   │
│            ConversationManager · DocumentAnalyzer · EmailService        │
│                                                                          │
│  AI Layer: LangChain (intent classifier, LLM calls)                    │
│            CrewAI    (specialist agents with DB tools)                  │
└───────────┬───────────────┬──────────────────┬──────────────────────────┘
            │               │                  │
            ▼               ▼                  ▼
     ┌────────────┐  ┌────────────┐   ┌──────────────┐
     │  MongoDB   │  │   Redis    │   │   ChromaDB   │
     │ (Primary)  │  │ (Sessions  │   │(Vector Search│
     │            │  │  + Cache)  │   │  optional)   │
     └────────────┘  └────────────┘   └──────────────┘
```

### Tech Stack at a Glance

| Layer             | Technology                             | Purpose                          |
| ----------------- | -------------------------------------- | -------------------------------- |
| Frontend          | Next.js 14 (App Router), TypeScript    | UI, Auth, Chat Interface         |
| API Server        | FastAPI, Uvicorn                       | REST endpoints, CORS, Lifespan   |
| AI – Intent       | LangChain + OpenAI (`gpt-4o-mini`)    | Intent classification            |
| AI – Agents       | CrewAI (Agents, Tasks, Crews)          | Domain-specific query execution  |
| AI – Doc Analysis | LangChain + OpenAI                     | PDF classification & extraction  |
| Primary DB        | MongoDB (Motor async + PyMongo sync)   | Students, Teachers, Courses, etc |
| Session Store     | Redis                                  | Chat sessions, token blacklist   |
| Vector DB         | ChromaDB (optional)                    | Semantic search over courses     |
| Email             | Python `smtplib` (SMTP/SSL/STARTTLS)  | Automated notifications          |
| Config            | Pydantic Settings + `.env`             | All environment variables        |

---

## 2. Project File Structure

```
university_data_analysis/
├── backend/
│   ├── main.py                          # ← ENTRY POINT (FastAPI app)
│   ├── config.py                        # Settings from .env (Pydantic)
│   ├── .env                             # Environment variables
│   │
│   ├── routers/                         # API endpoint definitions
│   │   ├── auth.py                      #   /auth/login, /auth/me, etc.
│   │   ├── chat.py                      #   /chat/session/start, /chat/message, /chat/upload_file
│   │   ├── assignments.py               #   /assignments/* CRUD
│   │   ├── report.py                    #   /report/* PDF generation
│   │   └── upload.py                    #   /upload/* generic file receive
│   │
│   ├── services/                        # Business logic layer
│   │   ├── auth.py                      #   AuthService: JWT, bcrypt, role detection
│   │   ├── chat_service.py              #   ChatService: orchestrates intent → CrewAI
│   │   ├── session_manager.py           #   SessionManager: Redis session CRUD
│   │   ├── conversation_manager.py      #   ConversationManager: LangChain chat memory
│   │   ├── document_analyzer.py         #   DocumentAnalyzer: LLM classify + email routing
│   │   ├── email_service.py             #   send_email / send_bulk_email via SMTP
│   │   ├── pdf_assignment_extract.py    #   _extract_pdf_text (pypdf)
│   │   ├── student_report_service.py    #   Academic report generation
│   │   ├── student_report_pdf.py        #   PDF rendering (ReportLab)
│   │   └── vector_store.py              #   ChromaDB indexing + search
│   │
│   ├── agents/                          # CrewAI multi-agent system
│   │   ├── university_crew.py           #   UniversityCrewFactory, AgentFactory, TaskFactory
│   │   ├── config/
│   │   │   ├── agents.yaml              #   Agent role/goal/backstory definitions
│   │   │   └── tasks.yaml               #   Task description templates
│   │   └── tools/
│   │       ├── database_tools.py        #   15+ MongoDB query tools for agents
│   │       └── platform_email_tools.py  #   CrewAI platform email tools
│   │
│   ├── utils/
│   │   ├── db.py                        #   MongoDBConnector (Motor async + sync)
│   │   └── query_scope.py              #   Assignment/grade reply scope detection
│   │
│   ├── new_dummy _data.py               #   Database seeder (all demo data)
│   └── uploads/                         #   Uploaded files storage
│
└── frontend/
    └── src/app/
        ├── login/page.tsx               # Login page
        ├── chat/page.tsx                # AI Chat interface
        ├── teacher/page.tsx             # Teacher dashboard
        ├── assignments/page.tsx         # Assignments view
        ├── settings/page.tsx            # Settings panel
        └── globals.css                  # Design system
```

---

## 3. Startup Flow — What Happens When You Run the Server

```
$ cd backend
$ python main.py
         │
         ▼
    main.py line 243-245:
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
         │
         ▼
    FastAPI app created (line 97):
    app = FastAPI(title="IBA Sukkur University Portal API", lifespan=lifespan)
         │
         ▼
    lifespan() context manager runs (line 46-86):
    ┌──────────────────────────────────────────────────┐
    │ 1. Load .env via get_settings() → config.py      │
    │    class Settings(BaseSettings) reads:            │
    │      MONGODB_URL, REDIS_URL, OPENAI_API_KEY, etc │
    │                                                    │
    │ 2. Connect MongoDB (Motor async):                 │
    │    await mongodb_connector.connect(url, db_name)  │
    │    → utils/db.py: MongoDBConnector.connect()      │
    │    → Pings admin, lists collections               │
    │                                                    │
    │ 3. Verify Redis:                                  │
    │    _check_redis(settings.redis_url)               │
    │    → redis.from_url(url).ping()                   │
    │                                                    │
    │ 4. Register routers:                              │
    │    app.include_router(auth_router)   → /auth/*    │
    │    app.include_router(chat_router)   → /chat/*    │
    │    app.include_router(report_router) → /report/*  │
    │    app.include_router(assignments_router)          │
    │    app.include_router(upload_router)               │
    │                                                    │
    │ ✅ Server ready at http://0.0.0.0:8000            │
    └──────────────────────────────────────────────────┘
```

**Key functions executed at startup:**

| Function | File | What it does |
|----------|------|-------------|
| `lifespan()` | `main.py:46` | Async context manager for app lifecycle |
| `get_settings()` | `config.py:66` | Cached Pydantic settings from `.env` |
| `mongodb_connector.connect()` | `utils/db.py:27` | Motor async client + ping |
| `_check_redis()` | `main.py:33` | Redis ping check |

---

## 4. Authentication Flow (Login → JWT → Protected Requests)

### 4.1 Login

```
Frontend POST /auth/login { email, password }
         │
         ▼
routers/auth.py → login() (line 109)
         │
         ▼
services/auth.py → AuthService.authenticate_user(email, password)  (line 145)
         │
         ├── get_user_by_email(email)  — scans: students → teachers → admins
         │   Returns: (user_doc, "student" | "teacher" | "admin")
         │
         └── verify_password(password, hashed)  — bcrypt via passlib
             If no hash stored: accepts "password123" (demo mode)
         │
         ▼
AuthService.create_tokens(user, role)  (line 225)
         │
         ├── create_access_token()  → JWT with {sub: user_id, email, role, exp: 30min}
         └── create_refresh_token() → JWT with {sub: user_id, email, role, exp: 7days}
         │
         ▼
Returns to frontend:
{
    access_token: "eyJ...",
    refresh_token: "eyJ...",
    role: "student",
    user: { user_id, full_name, email, department, roll_number, semester, ... }
}
```

### 4.2 Protected Requests

```python
# Every protected endpoint uses FastAPI Depends():
@router.get("/auth/me")
async def get_me(user: UserAuth = Depends(get_current_user)):
    #                                     ↑
    # services/auth.py line 338:
    # 1. Extracts token from Authorization header
    # 2. auth_service.verify_token(token) → checks Redis blacklist, decodes JWT
    # 3. auth_service.get_user_by_id(user_id, role) → fetches from MongoDB
    # 4. Returns UserAuth(user_id, email, full_name, role, department)
```

### 4.3 Logout

```
POST /auth/logout  (with Bearer token)
         │
         ▼
AuthService.blacklist_token(token)  (line 271)
    → Redis: SET blacklist:{token} = "1" EXPIRE {remaining_ttl}
    → Token can never be used again
```

---

## 5. Chat Message Flow — The Core AI Pipeline

This is the **main feature** — a user sends a text message and gets an intelligent response.

```
User types: "meri fees ka status batao"
                     │
                     ▼
Frontend: POST /chat/message  { session_id, message }
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  routers/chat.py → send_message() (line 182)                      │
│       ↓                                                             │
│  service.chat(session_id, message)                                 │
│       ↓                                                             │
│  services/chat_service.py → ChatService.chat() (line 191)         │
└─────────────────────────────────────────────────────────────────────┘
                     │
        ┌────────────┼────────────────────────────────────┐
        │            │                                    │
      STEP 1       STEP 2                              STEP 3
   Validate      Get Context                    Classify Intent
   Session       & History                      (LangChain)
        │            │                                    │
        ▼            ▼                                    ▼
```

### Step 1: Validate Session (Redis)

```python
# chat_service.py line 206
session = self.session_manager.get_session(session_id)
# → Redis GET session:{id} → deserialise JSON → StudentSession dataclass
# → Refresh TTL: Redis EXPIRE session:{id} 1800
```

### Step 2: Load Conversation Context (LangChain + Redis)

```python
# chat_service.py line 220
conv_manager = ConversationManagerFactory.get_manager(session_id, session)
conversation_history = conv_manager.get_conversation_context()
# → conversation_manager.py line 157
# → SessionChatHistory.get_context_string(n=10)
# → Redis GET chat_history:{session_id} → parse JSON → last 10 messages
# → Returns formatted string:
#   "Student: meri fees batao\nAssistant: Your fee is..."
```

### Step 3: Intent Classification (LangChain)

```python
# chat_service.py line 227-238
# For students:
intent = self.intent_classifier.classify(query, student_context, conversation_history)

# IntentClassifier (line 47):
# Uses ChatOpenAI(model="gpt-4o-mini", temperature=0)
# Prompt: "You are an intent classifier... classify into:
#          ASSIGNMENT | FEE | EXAM | GRADE | DOCUMENT | ATTENDANCE |
#          TIMETABLE | LIBRARY | SCHOLARSHIP | HOSTEL | COMPLAINT |
#          ANNOUNCEMENT | EMAIL | GENERAL"
# LLM returns: "FEE"

# For teachers: intent = "TEACHER" (always)
# For admins:   intent = "ADMIN"   (always)
```

### Step 4: Execute with CrewAI Agent

```python
# chat_service.py line 248-255
response_text = self._execute_with_crewai(intent, query, student_context, ...)

# _execute_with_crewai() (line 276):
factory = UniversityCrewFactory(tenant_id=tenant_id)
crew = factory.create_specialist_crew(intent="FEE", query=query, student_context=context)
result = crew.kickoff()
```

**Inside CrewAI — what actually happens:**

```
agents/university_crew.py
         │
         ▼
UniversityCrewFactory.create_specialist_crew(intent="FEE", ...)
         │
         ├── AgentFactory.create_specialist_agent("FEE")
         │     ├── Loads config/agents.yaml → fee_agent definition
         │     │     role: "Fee Management Specialist"
         │     │     goal: "Help students with fee queries..."
         │     │     backstory: "You are the finance department AI..."
         │     │
         │     └── ToolFactory.get_tools_for_intent("FEE")
         │           Returns: [FeeQueryTool(), StudentInfoTool()]
         │                          ↑
         │      agents/tools/database_tools.py (line ~500):
         │      class FeeQueryTool:
         │          def _run(self, student_id, semester=None):
         │              db = MongoClient(...)["iba_suk_portal"]
         │              fees = db["fees"].find({"student_id": ObjectId(...)})
         │              return json.dumps(fee_records)
         │
         ├── TaskFactory.create_specialist_task("FEE", query, context)
         │     Loads config/tasks.yaml → check_fee_status_task
         │     description: "Student {student_name} is asking: {query}...
         │                   Use the FeeQueryTool to get their fee status."
         │
         └── Crew(agents=[fee_agent], tasks=[fee_task], process=sequential)
              crew.kickoff()
              → Agent reads task → calls FeeQueryTool._run() → gets data
              → LLM generates natural language response
              → Returns: "Ali Khan, your semester 3 fees: Total Rs.150,000..."
```

### Step 5: Save to Conversation Memory

```python
# chat_service.py line 261
conv_manager.add_exchange(message, response_text)
# → conversation_manager.py → SessionChatHistory.add_message()
# → Redis SETEX chat_history:{session_id} 1800 [... messages JSON ...]
```

### Step 6: Return to Frontend

```python
return ChatResponse(
    session_id=session_id,
    message="Ali Khan, your semester 3 fees: Total Rs.150,000...",
    intent="FEE",
    student_name="Ali Khan",
    timestamp="2026-04-24T18:30:00",
    processing_time_ms=2345.67
)
```

---

## 6. Document Upload Flow — Agentic PDF Processing

When a user uploads a PDF through the chat, the system **autonomously classifies** the document, **saves it to the database** (if it's an assignment), and **sends email notifications** to the right people.

### 6.1 Teacher Uploads an Assignment PDF

```
Teacher uploads: "NLP_Assignment.pdf"
                     │
                     ▼
Frontend: POST /chat/upload_file  (multipart: session_id + file)
                     │
                     ▼
routers/chat.py → chat_file_upload_endpoint() (line 412)
                     │
    ┌────────────────┼────────────────────────────────────┐
    │                │                                    │
  READ PDF     GET SESSION                       ANALYZE DOC
    │                │                                    │
    ▼                ▼                                    ▼
```

**Step 1: Extract PDF Text**

```python
# routers/chat.py line 431
text = _extract_pdf_text(body)
# → services/pdf_assignment_extract.py
# → Uses pypdf.PdfReader to extract all page text
```

**Step 2: Get Uploader Identity from Session**

```python
# routers/chat.py line 442-449
session = service.get_session(session_id)
user_role = session.user_role     # "teacher"
user_id = session.student_id      # MongoDB ObjectId of the teacher
user_name = session.student_name  # "Dr. Ghulam Mujtaba"
```

**Step 3: LLM Classifies the Document**

```python
# services/document_analyzer.py → handle_document_upload() (line 258)
#     ↓
# classify_document(text, filename, uploader_role="teacher") (line 45)

# LLM Prompt (line 68):
# "You are a document classifier for a university portal.
#  The uploader's role is: teacher.
#  Classify into: assignment | submission | transcript | fee | ...
#  Extract: course_hint, course_subject_hint, key_dates, summary..."

# LLM returns:
{
    "document_type": "assignment",
    "notify_target": "students",
    "course_hint": null,
    "course_subject_hint": "Natural Language Processing",
    "summary": "NLP assignment on TF-IDF and Word2Vec...",
    "key_dates": [
        {"label": "Due date", "date": "2026-05-08"}
    ]
}
```

**Step 4: Save Assignment to Database**

```python
# document_analyzer.py → _save_assignment_to_db() (line 382)

# 3-Strategy Course Matching:
#   Strategy 1: Exact code match ("CS301" → CS301) ✗ (no code in PDF)
#   Strategy 2: Subject name match:
#     course_subject_hint = "Natural Language Processing"
#     Teacher's courses from DB:
#       CS301 = "Advanced NLP"           ← "nlp" ∩ "nlp" → MATCH ✓
#       CS302 = "Database Systems"
#   Strategy 3: Fallback to first course

# Creates assignment record:
db["assignments"].insert_one({
    "title": "NLP Assignment: TF-IDF vs Word2Vec",
    "course_code": "CS301",
    "course_id": ObjectId("..."),
    "teacher_id": ObjectId("..."),
    "due_date": datetime(2026, 5, 8),
    "source": "chat_upload",
    ...
})

# Creates pending submissions for enrolled students:
db["assignment_submissions"].insert_many([
    {"student_id": ObjectId("shuaib"), "status": "pending", ...},
    {"student_id": ObjectId("ali"),    "status": "pending", ...},
    {"student_id": ObjectId("maria"),  "status": "pending", ...},
])
```

**Step 5: Resolve Email Recipients**

```python
# document_analyzer.py → _resolve_recipients("students", "teacher", teacher_id)
# → _get_enrolled_students_for_teacher(teacher_id)
# → Finds teacher's courses → finds enrollments → gets student emails
# Returns: [
#   {"email": "shuaib@iba-suk.edu.pk", "full_name": "Shuaib"},
#   {"email": "ali@iba-suk.edu.pk",    "full_name": "Ali"},
#   {"email": "maria@iba-suk.edu.pk",  "full_name": "Maria"},
# ]
```

**Step 6: Send Emails**

```python
# document_analyzer.py → _send_notification_email()
# → services/email_service.py → send_bulk_email(recipients, subject, body_lines)
# → For each recipient: smtplib.SMTP (port 587 STARTTLS) or SMTP_SSL (port 465)
# → Subject: "📄 New Assignment uploaded by Dr. Ghulam Mujtaba"
```

**Step 7: Return Chat Reply**

```
📄 **Document:** NLP Assignment: TF-IDF vs Word2Vec
**Type:** Assignment
**Summary:** This document outlines an assignment for Advanced NLP...
**Key Dates:** Due date: 2026-05-08

📝 Assignment published to **Advanced NLP (CS301)** (due: 2026-05-08). 3 student(s) can now see it.
✅ Emails sent to 3 recipient(s) in **enrolled students**.
```

---

### 6.2 Student Submits an Assignment PDF

```
Student uploads: "NLP_Submission_Shuaib.pdf"
                     │
                     ▼
Same endpoint: POST /chat/upload_file
                     │
                     ▼
LLM classifies → document_type: "submission" (because uploader_role = "student")
                 course_subject_hint: "Natural Language Processing"
                 notify_target: "course_teacher"
                     │
                     ▼
_handle_student_submission() (document_analyzer.py line 585)
    │
    ├── Find student's enrolled courses from DB
    ├── Match "Natural Language Processing" → CS301 "Advanced NLP" ✓
    ├── Find pending submission in assignment_submissions
    ├── Update: status "pending" → "submitted", set submitted_at
    ├── Find teacher for CS301 → Dr. Ghulam Mujtaba
    └── Return teacher_email for notification
                     │
                     ▼
Email sent to teacher:
    Subject: "📄 New Submission uploaded by Shuaib"
    Body: "Document: NLP assignment submission for Advanced NLP..."
                     │
                     ▼
Chat reply to student:
    "📄 Document: NLP_Submission_Shuaib.pdf
     Type: Submission
     ✅ Email sent to 1 recipient(s) in Course Teacher."
```

---

## 7. All CrewAI Agents & Their Tools

The system uses **15+ specialist agents**, each with dedicated MongoDB query tools.

```
┌────────────────────────────────────────────────────────────────────────┐
│                     AGENT REGISTRY                                     │
│                agents/university_crew.py → AgentFactory                │
├───────────────┬─────────────────────────┬──────────────────────────────┤
│ Intent        │ Agent (agents.yaml)     │ Tools (database_tools.py)    │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ ASSIGNMENT    │ assignment_agent        │ AssignmentQueryTool          │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ FEE           │ fee_agent               │ FeeQueryTool                 │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ EXAM          │ exam_agent              │ ExamQueryTool                │
│               │                         │ AdmitCardQueryTool           │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ GRADE         │ grade_agent             │ GradeQueryTool               │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ DOCUMENT      │ document_agent          │ RecordsQueryTool             │
│               │                         │ FeeQueryTool                 │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ ATTENDANCE    │ attendance_agent        │ AttendanceQueryTool          │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ TIMETABLE     │ timetable_agent         │ TimetableQueryTool           │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ LIBRARY       │ library_agent           │ LibraryQueryTool             │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ SCHOLARSHIP   │ scholarship_agent       │ ScholarshipQueryTool         │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ HOSTEL        │ hostel_agent            │ HostelQueryTool              │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ COMPLAINT     │ complaint_agent         │ ComplaintQueryTool           │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ ANNOUNCEMENT  │ announcement_agent      │ AnnouncementQueryTool        │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ EMAIL         │ email_agent             │ Platform Email Tools         │
│               │                         │ StudentInfoTool              │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ TEACHER       │ teacher_portal_agent    │ TeacherTeachingQueryTool     │
│               │                         │ StudentInfoTool              │
│               │                         │ AnnouncementQueryTool        │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ ADMIN         │ admin_portal_agent      │ StudentInfoTool              │
│               │                         │ AnnouncementQueryTool        │
├───────────────┼─────────────────────────┼──────────────────────────────┤
│ GENERAL       │ general_assistant       │ StudentInfoTool              │
└───────────────┴─────────────────────────┴──────────────────────────────┘
```

**How agents are configured (YAML):**

```yaml
# agents/config/agents.yaml (excerpt)
fee_agent:
  role: "Fee Management Specialist"
  goal: "Accurately retrieve and present fee information for students"
  backstory: >
    You are the finance department's AI assistant at IBA Sukkur.
    You have access to all fee records and can help students
    understand their payment status, due dates, and challans.

# agents/config/tasks.yaml (excerpt)  
check_fee_status_task:
  description: >
    Student {student_name} (Roll: {roll_number}, Semester: {semester})
    is asking about fees: "{query}"
    Use the FeeQueryTool to fetch their fee records and provide
    a clear summary of their payment status.
  expected_output: "A clear, friendly summary of the student's fee status"
```

---

## 8. MongoDB Collections & Relations

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         CORE COLLECTIONS                                 │
├──────────────────────┬───────────────────────────────────────────────────┤
│ students             │ { _id, full_name, email, roll_number, semester,  │
│                      │   department, batch, cgpa, password }            │
├──────────────────────┼───────────────────────────────────────────────────┤
│ teachers             │ { _id, full_name, email, employee_id,           │
│                      │   department, designation,                       │
│                      │   assigned_course_codes: ["CS301", "CS302"] }   │
├──────────────────────┼───────────────────────────────────────────────────┤
│ admins               │ { _id, full_name, email, role }                 │
├──────────────────────┼───────────────────────────────────────────────────┤
│ courses              │ { _id, course_code, course_name, department,    │
│                      │   semester, credits, is_active }                │
├──────────────────────┼───────────────────────────────────────────────────┤
│ enrollments          │ { student_id, course_id, course_code, status }  │
├──────────────────────┼───────────────────────────────────────────────────┤
│ assignments          │ { _id, title, course_code, teacher_id,          │
│                      │   due_date, opens_at, source }                  │
├──────────────────────┼───────────────────────────────────────────────────┤
│ assignment_submissions│{ student_id, assignment_id, course_code,       │
│                      │   status: "pending"|"submitted", submitted_at } │
├──────────────────────┼───────────────────────────────────────────────────┤
│ fees                 │ { student_id, semester, total_fee, paid,        │
│                      │   remaining, due_date, status }                 │
├──────────────────────┼───────────────────────────────────────────────────┤
│ exams                │ { course_code, exam_type, date, venue, time }   │
├──────────────────────┼───────────────────────────────────────────────────┤
│ grades               │ { student_id, course_code, grade, semester }    │
└──────────────────────┴───────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                     CROSS-REFERENCE COLLECTIONS                          │
├──────────────────────┬───────────────────────────────────────────────────┤
│ course_teacher_map   │ { course_code, course_name, teacher_id,         │
│                      │   teacher_name, enrolled_students: [...] }      │
├──────────────────────┼───────────────────────────────────────────────────┤
│ teacher_student_     │ { teacher_id, teacher_name,                     │
│ relations            │   students: [{ student_id, name, courses }] }   │
├──────────────────────┼───────────────────────────────────────────────────┤
│ student_course_      │ { student_id, student_name,                     │
│ teachers             │   courses: [{ code, name, teacher_name }] }    │
└──────────────────────┴───────────────────────────────────────────────────┘
```

---

## 9. Session & Memory Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    REDIS KEY STRUCTURE                           │
├───────────────────────────┬─────────────────────────────────────┤
│ session:{uuid}            │ JSON blob of StudentSession         │
│                           │ TTL: 1800s (30 min)                 │
│                           │ Contains: student_id, name, role,   │
│                           │           department, semester, etc  │
├───────────────────────────┼─────────────────────────────────────┤
│ chat_history:{uuid}       │ JSON array of messages              │
│                           │ TTL: 1800s (30 min)                 │
│                           │ [{"type":"human","content":"..."},  │
│                           │  {"type":"ai","content":"..."}]     │
├───────────────────────────┼─────────────────────────────────────┤
│ blacklist:{jwt_token}     │ "1"                                 │
│                           │ TTL: remaining token expiry          │
│                           │ Prevents reuse after logout          │
└───────────────────────────┴─────────────────────────────────────┘
```

**Memory flow per request:**

```python
# 1. SessionManager (session_manager.py)
session_manager.create_session()    # Login  → Redis SET session:{id}
session_manager.get_session(id)     # Each request → Redis GET
session_manager.refresh_session(id) # Each request → Redis EXPIRE (reset TTL)
session_manager.delete_session(id)  # Logout → Redis DEL

# 2. ConversationManager (conversation_manager.py)
conv_mgr.add_exchange(user_msg, ai_msg)  # After each chat → Redis SETEX
conv_mgr.get_conversation_context()      # Before each chat → Redis GET → format
conv_mgr.get_chat_history()              # For /history endpoint
```

---

## 10. Email Notification System

```
services/email_service.py
         │
         ├── is_configured() → checks SMTP_USER + SMTP_PASSWORD in .env
         │
         ├── send_email(to, subject, body_lines)
         │     ├── Build MIMEMultipart (plain + HTML)
         │     ├── Port 465 → SMTP_SSL
         │     └── Port 587 → SMTP + STARTTLS
         │
         └── send_bulk_email(recipients, subject, body_lines)
               └── Loop: send_email() for each → returns {sent, failed, total}
```

**Email triggers:**

| Trigger | Sender Role | Recipients | Email Subject |
|---------|------------|------------|---------------|
| Assignment uploaded | Teacher | Enrolled students | "📄 New Assignment uploaded by Dr. ..." |
| Submission uploaded | Student | Course teacher | "📄 New Submission uploaded by ..." |
| Transcript request | Student | Exam office staff | "📄 New Transcript uploaded by ..." |
| Fee document | Student | Finance staff | "📄 New Fee uploaded by ..." |
| Complaint | Any | Admin staff | "📄 New Complaint uploaded by ..." |

---

## 11. Frontend Architecture

### Key Pages and What They Call

```
/login/page.tsx
    → POST /auth/login { email, password }
    → Stores tokens in localStorage
    → Redirects to /chat

/chat/page.tsx
    → On mount: POST /chat/session/start { student_id, email, user_role }
    → On message: POST /chat/message { session_id, message }
    → On file upload: POST /chat/upload_file (FormData: session_id + file)
    → Academic Report button: POST /report/generate
    → On logout: POST /auth/logout + POST /chat/session/{id}/end

/teacher/page.tsx
    → GET /auth/me/teacher (teacher details)
    → Same chat interface with teacher-specific features
```

### Auth Context (React)

```typescript
// The frontend wraps the app in an AuthProvider that:
// 1. Reads JWT from localStorage on mount
// 2. Calls GET /auth/me to validate
// 3. If expired, calls POST /auth/refresh with refresh_token
// 4. Provides { user, token, login(), logout() } via React Context
```

---

## 12. Complete Request-to-Response Trace

Here's a **single request traced** through every layer:

```
Student Shuaib asks: "show my pending assignments"

──────────────────────────────────────────────────────────────
LAYER 1: FRONTEND (chat/page.tsx)
──────────────────────────────────────────────────────────────
→ fetch("http://localhost:8000/chat/message", {
    method: "POST",
    headers: { "Authorization": "Bearer eyJ...", "Content-Type": "application/json" },
    body: { "session_id": "abc-123", "message": "show my pending assignments" }
  })

──────────────────────────────────────────────────────────────
LAYER 2: ROUTER (routers/chat.py line 182)
──────────────────────────────────────────────────────────────
→ send_message(request, service=Depends(get_service))
→ service = get_chat_service()  # singleton ChatService
→ service.chat(session_id="abc-123", message="show my pending assignments")

──────────────────────────────────────────────────────────────
LAYER 3: CHAT SERVICE (services/chat_service.py line 191)
──────────────────────────────────────────────────────────────
→ session = session_manager.get_session("abc-123")
    Redis: GET session:abc-123 → StudentSession(student_id="672...", 
           student_name="Shuaib", roll_number="CS-2023-003", 
           semester=3, department="CS", user_role="student")

→ conv_manager = ConversationManagerFactory.get_manager("abc-123", session)
→ conversation_history = conv_manager.get_conversation_context()
    Redis: GET chat_history:abc-123 → "No previous conversation."

→ intent = intent_classifier.classify("show my pending assignments", context)
    LangChain: ChatOpenAI("gpt-4o-mini").invoke(prompt) → "ASSIGNMENT"

→ assignment_reply_scope = detect_assignment_reply_scope("show my pending...")
    → returns "PENDING"

──────────────────────────────────────────────────────────────
LAYER 4: CREWAI EXECUTION (agents/university_crew.py)
──────────────────────────────────────────────────────────────
→ factory = UniversityCrewFactory(tenant_id="default")
→ specialist = AgentFactory.create_specialist_agent("ASSIGNMENT")
    → Loads agents.yaml → assignment_agent config
    → Tools: [AssignmentQueryTool(), StudentInfoTool()]

→ task = TaskFactory.create_specialist_task("ASSIGNMENT", query, context)
    → Loads tasks.yaml → fetch_assignments_task
    → Injects: student_name="Shuaib", roll_number="CS-2023-003",
               assignment_reply_scope="Show only PENDING assignments"

→ crew = Crew(agents=[specialist], tasks=[task])
→ crew.kickoff()

    AGENT THINKS: "I need to find Shuaib's assignments. Let me use the tool."
    AGENT CALLS: AssignmentQueryTool._run(student_id="672...", status="pending")
        → MongoDB: db.assignment_submissions.find({student_id: ..., status: "pending"})
        → Joins with db.assignments for titles and due dates
        → Returns JSON: [{title: "NLP Assignment", due: "2026-05-08", course: "CS301"}, ...]

    AGENT GENERATES: "Hello Shuaib! You have 3 pending assignments:
                      1. NLP Assignment for Advanced NLP (CS301), due May 8
                      2. ..."

──────────────────────────────────────────────────────────────
LAYER 5: SAVE + RETURN (services/chat_service.py)
──────────────────────────────────────────────────────────────
→ conv_manager.add_exchange("show my pending assignments", response)
    Redis: SETEX chat_history:abc-123 1800 [... updated messages ...]

→ return ChatResponse(message="Hello Shuaib! You have 3...", intent="ASSIGNMENT", ...)

──────────────────────────────────────────────────────────────
LAYER 6: FRONTEND RENDERS
──────────────────────────────────────────────────────────────
→ Chat bubble appears with the response
```

---

## 13. Environment Variables (.env)

```env
# Database
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=iba_suk_portal

# Cache / Sessions
REDIS_URL=redis://localhost:6379
SESSION_TTL_SECONDS=1800

# AI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Auth
JWT_SECRET_KEY=your-super-secret-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
```

---

## 14. How to Run

```bash
# Terminal 1: Start MongoDB
mongod

# Terminal 2: Start Redis
redis-server

# Terminal 3: Seed database
cd backend
python "new_dummy _data.py"

# Terminal 4: Start backend
cd backend
python main.py
# → Server at http://localhost:8000
# → Swagger docs at http://localhost:8000/docs

# Terminal 5: Start frontend
cd frontend
npm run dev
# → UI at http://localhost:3000
```

---

## 15. Key Function Reference

| Function | File | Purpose |
|----------|------|---------|
| `lifespan()` | `main.py:46` | App startup: connect MongoDB + Redis |
| `AuthService.authenticate_user()` | `services/auth.py:145` | Email lookup + bcrypt verify |
| `AuthService.create_tokens()` | `services/auth.py:225` | JWT access + refresh token pair |
| `get_current_user()` | `services/auth.py:338` | FastAPI dependency: decode JWT |
| `ChatService.chat()` | `services/chat_service.py:191` | Main chat pipeline orchestrator |
| `IntentClassifier.classify()` | `services/chat_service.py:96` | LangChain intent detection |
| `UniversityCrewFactory.create_specialist_crew()` | `agents/university_crew.py:398` | Build CrewAI crew for intent |
| `AgentFactory.create_specialist_agent()` | `agents/university_crew.py:248` | Load YAML config + tools |
| `ToolFactory.get_tools_for_intent()` | `agents/university_crew.py:143` | Map intent → DB query tools |
| `SessionManager.create_session()` | `services/session_manager.py:~100` | MongoDB lookup + Redis SET |
| `ConversationManager.add_exchange()` | `services/conversation_manager.py:143` | Save chat to Redis |
| `classify_document()` | `services/document_analyzer.py:45` | LLM document classification |
| `handle_document_upload()` | `services/document_analyzer.py:258` | Full upload pipeline |
| `_save_assignment_to_db()` | `services/document_analyzer.py:382` | Assignment persistence + NLP course match |
| `_handle_student_submission()` | `services/document_analyzer.py:585` | Submission record + teacher notification |
| `_resolve_recipients()` | `services/document_analyzer.py:195` | Map doc type → email targets |
| `send_bulk_email()` | `services/email_service.py:100` | SMTP bulk send |
| `_extract_pdf_text()` | `services/pdf_assignment_extract.py` | pypdf text extraction |
