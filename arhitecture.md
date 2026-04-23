# IBA Sukkur University Portal - System Architecture

## Overview

This document describes the complete system architecture for the AI-powered university portal that supports both students and teachers with role-based access control.

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    FRONTEND                                          │
│                                   (Next.js)                                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐                 │
│   │   Login    │   │ Dashboard  │   │    Chat    │   │  Profile   │                 │
│   │   Page     │   │   Page     │   │  Interface │   │   Page     │                 │
│   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘                 │
│         │                │                │                │                         │
│         └────────────────┴────────────────┴────────────────┘                         │
│                                    │                                                 │
│                          ┌─────────┴─────────┐                                       │
│                          │   Auth Context    │                                       │
│                          │  (Token Storage)  │                                       │
│                          └─────────┬─────────┘                                       │
│                                    │                                                 │
└────────────────────────────────────┼─────────────────────────────────────────────────┘
                                     │
                                     │ HTTP/REST API
                                     │ Authorization: Bearer <token>
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    BACKEND                                           │
│                                   (FastAPI)                                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                            API ROUTERS                                       │   │
│   ├─────────────────────────────────────────────────────────────────────────────┤   │
│   │                                                                              │   │
│   │  ┌──────────────────┐              ┌──────────────────┐                     │   │
│   │  │   Auth Router    │              │   Chat Router    │                     │   │
│   │  │  /auth/*         │              │  /chat/*         │                     │   │
│   │  ├──────────────────┤              ├──────────────────┤                     │   │
│   │  │ POST /login      │              │ POST /session/   │                     │   │
│   │  │ POST /logout     │              │      start       │                     │   │
│   │  │ POST /refresh    │              │ POST /message    │                     │   │
│   │  │ GET  /me         │              │ GET  /history    │                     │   │
│   │  │ GET  /verify     │              │ POST /end        │                     │   │
│   │  └──────────────────┘              └──────────────────┘                     │   │
│   │                                                                              │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                            SERVICES LAYER                                    │   │
│   ├─────────────────────────────────────────────────────────────────────────────┤   │
│   │                                                                              │   │
│   │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │   │
│   │  │ Auth Service │   │Chat Service  │   │ Session Mgr  │   │ Conv. Manager│  │   │
│   │  │              │   │              │   │              │   │              │  │   │
│   │  │ - JWT Token  │   │ - Intent     │   │ - Create     │   │ - Chat       │  │   │
│   │  │ - Password   │   │   Detection  │   │ - Get        │   │   History    │  │   │
│   │  │ - Role Check │   │ - Agent      │   │ - Delete     │   │ - Context    │  │   │
│   │  │ - Blacklist  │   │   Execution  │   │ - Refresh    │   │ - Memory     │  │   │
│   │  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘  │   │
│   │                                                                              │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                          AI PROCESSING LAYER                                 │   │
│   │                         (CrewAI + LangChain)                                 │   │
│   ├─────────────────────────────────────────────────────────────────────────────┤   │
│   │                                                                              │   │
│   │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │   │
│   │  │   Intent     │   │   Agent      │   │  Specialist  │   │  Response    │  │   │
│   │  │  Classifier  │──▶│   Factory    │──▶│   Agents     │──▶│  Generator   │  │   │
│   │  │              │   │              │   │              │   │              │  │   │
│   │  │ ASSIGNMENT   │   │ Create agent │   │ - Assignment │   │ Natural      │  │   │
│   │  │ FEE          │   │ based on     │   │ - Fee        │   │ Language     │  │   │
│   │  │ EXAM         │   │ intent       │   │ - Exam       │   │ Response     │  │   │
│   │  │ GRADE        │   │              │   │ - Grade      │   │              │  │   │
│   │  │ DOCUMENT     │   │              │   │ - Document   │   │              │  │   │
│   │  │ GENERAL      │   │              │   │ - Router     │   │              │  │   │
│   │  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘  │   │
│   │                                                                              │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  DATA LAYER                                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐          │
│  │      MongoDB        │  │       Redis         │  │     ChromaDB        │          │
│  │   (Primary Data)    │  │  (Cache/Sessions)   │  │  (Vector Search)    │          │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤          │
│  │                     │  │                     │  │                     │          │
│  │ Collections:        │  │ Keys:               │  │ Collections:        │          │
│  │ - students          │  │ - session:{id}      │  │ - courses           │          │
│  │ - teachers          │  │ - chat_history:{id} │  │ - assignments       │          │
│  │ - admins            │  │ - blacklist:{token} │  │                     │          │
│  │ - courses           │  │                     │  │ Semantic search     │          │
│  │ - assignments       │  │ TTL: 30 minutes     │  │ for AI context      │          │
│  │ - fees              │  │                     │  │                     │          │
│  │ - exams             │  │                     │  │                     │          │
│  │ - grades            │  │                     │  │                     │          │
│  │                     │  │                     │  │                     │          │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘          │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Authentication Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              LOGIN FLOW                                              │
└─────────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐                    ┌──────────┐                    ┌──────────┐
  │ Frontend │                    │  Backend │                    │ Database │
  └────┬─────┘                    └────┬─────┘                    └────┬─────┘
       │                               │                               │
       │  POST /auth/login             │                               │
       │  {email, password}            │                               │
       │──────────────────────────────▶│                               │
       │                               │                               │
       │                               │  Find email in collections    │
       │                               │──────────────────────────────▶│
       │                               │                               │
       │                               │  Check: students → teachers   │
       │                               │         → admins              │
       │                               │◀──────────────────────────────│
       │                               │  Return: user + role          │
       │                               │                               │
       │                               │  Verify password              │
       │                               │  Generate JWT tokens          │
       │                               │                               │
       │  {access_token, refresh_token,│                               │
       │   role, user}                 │                               │
       │◀──────────────────────────────│                               │
       │                               │                               │
       │  Store token in localStorage  │                               │
       │  Redirect based on role       │                               │
       │                               │                               │
       ▼                               ▼                               ▼


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           PROTECTED REQUEST FLOW                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐                    ┌──────────┐                    ┌──────────┐
  │ Frontend │                    │  Backend │                    │  Redis   │
  └────┬─────┘                    └────┬─────┘                    └────┬─────┘
       │                               │                               │
       │  GET /auth/me                 │                               │
       │  Authorization: Bearer <token>│                               │
       │──────────────────────────────▶│                               │
       │                               │                               │
       │                               │  Check blacklist              │
       │                               │──────────────────────────────▶│
       │                               │◀──────────────────────────────│
       │                               │  Not blacklisted ✓            │
       │                               │                               │
       │                               │  Verify JWT signature         │
       │                               │  Check expiration             │
       │                               │  Extract user_id + role       │
       │                               │                               │
       │  {user_id, email, role, ...}  │                               │
       │◀──────────────────────────────│                               │
       │                               │                               │
       ▼                               ▼                               ▼


┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              LOGOUT FLOW                                             │
└─────────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐                    ┌──────────┐                    ┌──────────┐
  │ Frontend │                    │  Backend │                    │  Redis   │
  └────┬─────┘                    └────┬─────┘                    └────┬─────┘
       │                               │                               │
       │  POST /auth/logout            │                               │
       │  Authorization: Bearer <token>│                               │
       │──────────────────────────────▶│                               │
       │                               │                               │
       │                               │  Add token to blacklist       │
       │                               │  SET blacklist:{token} = 1    │
       │                               │  EXPIRE = token_exp_time      │
       │                               │──────────────────────────────▶│
       │                               │◀──────────────────────────────│
       │                               │                               │
       │  {success: true}              │                               │
       │◀──────────────────────────────│                               │
       │                               │                               │
       │  Clear localStorage           │                               │
       │  Redirect to /login           │                               │
       │                               │                               │
       ▼                               ▼                               ▼
```

---

## Chat Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              CHAT MESSAGE FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘

  User Input: "meri fees ka status batao"
       │
       ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ STEP 1: SESSION VALIDATION                                                      │
  │ - Check if session exists in Redis                                              │
  │ - Refresh session TTL                                                           │
  │ - Load student context                                                          │
  └────────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ STEP 2: INTENT CLASSIFICATION (LangChain)                                       │
  │                                                                                 │
  │ Input: "meri fees ka status batao"                                              │
  │                                                                                 │
  │ ┌─────────────────────────────────────────────────────────────────────────┐    │
  │ │ ChatOpenAI (gpt-4o-mini)                                                 │    │
  │ │                                                                          │    │
  │ │ System: You are an intent classifier...                                  │    │
  │ │ Categories: ASSIGNMENT | FEE | EXAM | GRADE | DOCUMENT | GENERAL        │    │
  │ │                                                                          │    │
  │ │ Output: "FEE"                                                            │    │
  │ └─────────────────────────────────────────────────────────────────────────┘    │
  │                                                                                 │
  └────────────────────────────────────────────────────────────────────────────────┘
       │
       │ Intent: FEE
       ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ STEP 3: AGENT SELECTION (CrewAI)                                                │
  │                                                                                 │
  │ Intent → Agent Mapping:                                                         │
  │ ┌─────────────┬─────────────────────┬──────────────────────────────────────┐   │
  │ │   Intent    │      Agent          │              Tools                    │   │
  │ ├─────────────┼─────────────────────┼──────────────────────────────────────┤   │
  │ │ ASSIGNMENT  │ Assignment Agent    │ AssignmentQueryTool, StudentInfoTool │   │
  │ │ FEE         │ Fee Agent           │ FeeQueryTool, StudentInfoTool        │   │
  │ │ EXAM        │ Exam Agent          │ ExamQueryTool, StudentInfoTool       │   │
  │ │ GRADE       │ Grade Agent         │ GradeQueryTool, StudentInfoTool      │   │
  │ │ DOCUMENT    │ Document Agent      │ FeeQueryTool, StudentInfoTool        │   │
  │ │ GENERAL     │ Router Agent        │ StudentInfoTool                      │   │
  │ └─────────────┴─────────────────────┴──────────────────────────────────────┘   │
  │                                                                                 │
  │ Selected: Fee Agent with FeeQueryTool                                           │
  │                                                                                 │
  └────────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ STEP 4: DATABASE QUERY                                                          │
  │                                                                                 │
  │ FeeQueryTool executes:                                                          │
  │ db.fees.find({student_id: "...", semester: 3})                                  │
  │                                                                                 │
  │ Result: {                                                                       │
  │   "total_fee": 150000,                                                          │
  │   "paid": 100000,                                                               │
  │   "remaining": 50000,                                                           │
  │   "due_date": "2024-03-15",                                                     │
  │   "status": "PARTIAL"                                                           │
  │ }                                                                               │
  │                                                                                 │
  └────────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ STEP 5: RESPONSE GENERATION                                                     │
  │                                                                                 │
  │ Agent generates natural language response:                                      │
  │                                                                                 │
  │ "Ali Khan, aapki semester 3 ki fees ka status:                                  │
  │  - Total Fee: Rs. 150,000                                                       │
  │  - Paid: Rs. 100,000                                                            │
  │  - Remaining: Rs. 50,000                                                        │
  │  - Due Date: March 15, 2024                                                     │
  │  - Status: PARTIAL PAYMENT                                                      │
  │                                                                                 │
  │  Please pay the remaining amount before the due date."                          │
  │                                                                                 │
  └────────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌────────────────────────────────────────────────────────────────────────────────┐
  │ STEP 6: SAVE TO CONVERSATION HISTORY                                            │
  │                                                                                 │
  │ Redis: chat_history:{session_id}                                                │
  │ [                                                                               │
  │   {type: "human", content: "meri fees ka status batao"},                        │
  │   {type: "ai", content: "Ali Khan, aapki semester 3 ki fees..."}                │
  │ ]                                                                               │
  │                                                                                 │
  └────────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  Return to Frontend
```

---

## API Endpoints Reference

### Authentication Endpoints (`/auth`)

| Method | Endpoint | Description | Auth Required | Request Body | Response |
|--------|----------|-------------|---------------|--------------|----------|
| POST | `/auth/login` | Login with email & password | No | `{email, password}` | `{access_token, refresh_token, role, user}` |
| POST | `/auth/logout` | Invalidate token | Yes | - | `{success, message}` |
| POST | `/auth/refresh` | Get new access token | No | `{refresh_token}` | `{access_token, refresh_token, ...}` |
| GET | `/auth/me` | Get current user info | Yes | - | `{user_id, email, full_name, role, ...}` |
| GET | `/auth/me/student` | Get student details | Yes (Student) | - | `{..., roll_number, semester, cgpa}` |
| GET | `/auth/me/teacher` | Get teacher details | Yes (Teacher) | - | `{..., employee_id, designation}` |
| GET | `/auth/verify` | Verify token validity | Yes | - | `{valid, user_id, role}` |

### Chat Endpoints (`/chat`)

| Method | Endpoint | Description | Auth Required | Request Body | Response |
|--------|----------|-------------|---------------|--------------|----------|
| POST | `/chat/session/start` | Start new chat session | No* | `{roll_number}` or `{email}` | `{session_id, student_name, ...}` |
| POST | `/chat/message` | Send message to AI | No* | `{session_id, message}` | `{message, intent, timestamp}` |
| GET | `/chat/session/{id}/history` | Get chat history | No* | - | `{messages[], count}` |
| GET | `/chat/session/{id}/status` | Check session status | No* | - | `{valid, remaining_seconds}` |
| POST | `/chat/session/{id}/end` | End chat session | No* | - | `{success, message}` |
| POST | `/chat/session/{id}/refresh` | Extend session TTL | No* | - | `{success, remaining_seconds}` |

*Note: Chat uses session-based auth, not JWT. Can be integrated with JWT if needed.

---

## Frontend Pages & Components

### Page Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout with AuthProvider
│   │   ├── page.tsx                # Landing page (redirect to login/dashboard)
│   │   │
│   │   ├── login/
│   │   │   └── page.tsx            # Login page
│   │   │
│   │   ├── dashboard/
│   │   │   ├── page.tsx            # Dashboard (role-based redirect)
│   │   │   ├── student/
│   │   │   │   └── page.tsx        # Student dashboard
│   │   │   └── teacher/
│   │   │       └── page.tsx        # Teacher dashboard
│   │   │
│   │   ├── chat/
│   │   │   └── page.tsx            # AI Chat interface
│   │   │
│   │   └── profile/
│   │       └── page.tsx            # User profile
│   │
│   ├── components/
│   │   ├── auth/
│   │   │   ├── LoginForm.tsx       # Login form component
│   │   │   ├── AuthGuard.tsx       # Protected route wrapper
│   │   │   └── RoleGuard.tsx       # Role-based access wrapper
│   │   │
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx      # Main chat container
│   │   │   ├── MessageList.tsx     # Message display
│   │   │   ├── MessageInput.tsx    # Input with send button
│   │   │   └── MessageBubble.tsx   # Individual message
│   │   │
│   │   ├── dashboard/
│   │   │   ├── StudentDashboard.tsx
│   │   │   ├── TeacherDashboard.tsx
│   │   │   ├── StatsCard.tsx
│   │   │   └── QuickActions.tsx
│   │   │
│   │   └── layout/
│   │       ├── Navbar.tsx          # Navigation bar
│   │       ├── Sidebar.tsx         # Side navigation
│   │       └── Footer.tsx
│   │
│   ├── contexts/
│   │   └── AuthContext.tsx         # Authentication context
│   │
│   ├── hooks/
│   │   ├── useAuth.ts              # Auth hook
│   │   └── useChat.ts              # Chat hook
│   │
│   ├── services/
│   │   ├── api.ts                  # Axios instance with interceptors
│   │   ├── authService.ts          # Auth API calls
│   │   └── chatService.ts          # Chat API calls
│   │
│   └── types/
│       ├── auth.ts                 # Auth types
│       └── chat.ts                 # Chat types
```

### UI Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 USER FLOW                                            │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────┐
                                    │  START  │
                                    └────┬────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │  Has Token in   │
                                │  localStorage?  │
                                └────────┬────────┘
                                         │
                        ┌────────────────┼────────────────┐
                        │ NO                             │ YES
                        ▼                                ▼
                ┌───────────────┐               ┌───────────────┐
                │  LOGIN PAGE   │               │ Verify Token  │
                │               │               │ GET /auth/me  │
                └───────┬───────┘               └───────┬───────┘
                        │                               │
                        │                       ┌───────┴───────┐
                        │                       │ Valid?        │
                        │                       └───────┬───────┘
                        │                  NO ──────────┼────────── YES
                        │                  │            │            │
                        │                  ▼            │            │
                        │          ┌─────────────┐     │            │
                        │          │Clear Token  │     │            │
                        │◀─────────│Redirect     │     │            │
                        │          └─────────────┘     │            │
                        │                              │            │
                        ▼                              │            ▼
                ┌───────────────┐                      │    ┌───────────────┐
                │ Enter Email & │                      │    │ Check Role    │
                │ Password      │                      │    └───────┬───────┘
                └───────┬───────┘                      │            │
                        │                              │    ┌───────┴───────┐
                        ▼                              │    │               │
                ┌───────────────┐                      │    ▼               ▼
                │POST /auth/    │                      │ STUDENT        TEACHER
                │    login      │                      │    │               │
                └───────┬───────┘                      │    ▼               ▼
                        │                              │ ┌─────────┐  ┌─────────┐
                ┌───────┴───────┐                      │ │ Student │  │ Teacher │
                │ Success?      │                      │ │Dashboard│  │Dashboard│
                └───────┬───────┘                      │ └────┬────┘  └────┬────┘
           NO ──────────┼────────── YES                │      │            │
           │            │            │                 │      └──────┬─────┘
           ▼            │            ▼                 │             │
   ┌───────────────┐    │    ┌───────────────┐        │             ▼
   │ Show Error    │    │    │ Store Token   │        │     ┌───────────────┐
   │ Message       │    │    │ in localStorage│◀───────┘     │    CHAT       │
   └───────────────┘    │    └───────┬───────┘              │   INTERFACE   │
                        │            │                       └───────────────┘
                        │            ▼
                        │    ┌───────────────┐
                        │    │ Redirect to   │
                        │    │ Dashboard     │
                        │    └───────────────┘
                        │
                        ▼
```

---

## Role-Based UI Components

### Student Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  [Logo] IBA Sukkur Portal                    [Profile] Ali Khan ▼  [Logout]         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  Welcome back, Ali Khan!                                          Semester 3 | CS   │
│                                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  Assignments   │  │     Fees       │  │     Exams      │  │     CGPA       │    │
│  │                │  │                │  │                │  │                │    │
│  │   3 Pending    │  │  Rs. 50,000    │  │  Next: 5 days  │  │     3.45       │    │
│  │                │  │   Remaining    │  │                │  │                │    │
│  └────────────────┘  └────────────────┘  └────────────────┘  └────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          QUICK ACTIONS                                       │   │
│  │                                                                              │   │
│  │  [💬 Chat with AI]  [📄 Request Document]  [💰 Pay Fees]  [📊 View Grades] │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─────────────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │        UPCOMING DEADLINES           │  │         RECENT ACTIVITY             │  │
│  │                                      │  │                                      │  │
│  │  📝 Database Assignment    Mar 15   │  │  ✓ Submitted AI Lab 3     Mar 10   │  │
│  │  📝 AI Project Proposal    Mar 18   │  │  ✓ Paid Fee Installment   Mar 08   │  │
│  │  📝 Networks Quiz          Mar 20   │  │  ✓ Viewed Exam Schedule   Mar 05   │  │
│  │                                      │  │                                      │  │
│  └─────────────────────────────────────┘  └─────────────────────────────────────┘  │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Teacher Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  [Logo] IBA Sukkur Portal                    [Profile] Dr. Ahmed ▼  [Logout]        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  Welcome back, Dr. Ahmed!                                    CS Department | Prof   │
│                                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │    Courses     │  │    Students    │  │  Assignments   │  │   Pending      │    │
│  │                │  │                │  │                │  │   Grades       │    │
│  │       4        │  │      120       │  │   8 Active     │  │      45        │    │
│  │   This Sem     │  │     Total      │  │                │  │   to Submit    │    │
│  └────────────────┘  └────────────────┘  └────────────────┘  └────────────────┘    │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          QUICK ACTIONS                                       │   │
│  │                                                                              │   │
│  │  [📝 Create Assignment]  [📊 Enter Grades]  [📋 View Attendance]  [💬 Chat]│   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─────────────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │          MY COURSES                  │  │       PENDING SUBMISSIONS          │  │
│  │                                      │  │                                      │  │
│  │  📚 Database Systems     CS-301     │  │  45 submissions need grading        │  │
│  │  📚 AI & ML              CS-401     │  │                                      │  │
│  │  📚 Computer Networks    CS-302     │  │  [Grade Now →]                       │  │
│  │  📚 Software Engg        CS-303     │  │                                      │  │
│  │                                      │  │                                      │  │
│  └─────────────────────────────────────┘  └─────────────────────────────────────┘  │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Chat Interface

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  [← Back]           AI Assistant                              [End Chat]            │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐    │   │
│  │  │ 🤖 AI Assistant                                           10:30 AM │    │   │
│  │  │                                                                     │    │   │
│  │  │ Assalam o Alaikum, Ali Khan! Main IBA Sukkur ka AI assistant      │    │   │
│  │  │ hoon. Aap mujhse apne assignments, fees, exams, ya grades ke      │    │   │
│  │  │ baare mein pooch sakte hain. Kaise madad kar sakta hoon?          │    │   │
│  │  └─────────────────────────────────────────────────────────────────────┘    │   │
│  │                                                                              │   │
│  │                    ┌─────────────────────────────────────────────────────┐  │   │
│  │                    │ 👤 You                                    10:31 AM │  │   │
│  │                    │                                                     │  │   │
│  │                    │ meri fees ka status batao                           │  │   │
│  │                    └─────────────────────────────────────────────────────┘  │   │
│  │                                                                              │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐    │   │
│  │  │ 🤖 AI Assistant                                           10:31 AM │    │   │
│  │  │                                                                     │    │   │
│  │  │ Ali Khan, aapki semester 3 ki fees ka status:                      │    │   │
│  │  │                                                                     │    │   │
│  │  │ 💰 Total Fee: Rs. 150,000                                          │    │   │
│  │  │ ✅ Paid: Rs. 100,000                                               │    │   │
│  │  │ ⏳ Remaining: Rs. 50,000                                           │    │   │
│  │  │ 📅 Due Date: March 15, 2024                                        │    │   │
│  │  │ 📊 Status: PARTIAL PAYMENT                                         │    │   │
│  │  │                                                                     │    │   │
│  │  │ Please pay the remaining amount before the due date.               │    │   │
│  │  └─────────────────────────────────────────────────────────────────────┘    │   │
│  │                                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  Type your message...                                            [Send ➤]  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  Quick Actions: [📝 Assignments] [💰 Fees] [📅 Exams] [📊 Grades] [📄 Documents]   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Token Storage & Management

