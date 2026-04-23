"""
IBA Sukkur — University Portal
Additional Collections Seed Script
------------------------------------
Run AFTER seed_university_db.py
Run: python seed_additional_db.py
Requires: pip install pymongo
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
from bson import ObjectId
import random

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
MONGO_URI    = "mongodb://localhost:27017"
DB_NAME      = "iba_suk_portal"
UNIVERSITY   = "IBA Sukkur"

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

# ─────────────────────────────────────────
# LOAD EXISTING IDs FROM PREVIOUS SEED
# ─────────────────────────────────────────
print("🔗  Loading existing data from iba_suk_portal...\n")

def get_student(username):
    user    = db["users"].find_one({"username": username})
    student = db["students"].find_one({"user_id": user["_id"]})
    return user, student

def get_course(code):
    return db["courses"].find_one({"course_code": code})

_, ali   = get_student("ali_cs")
_, sara  = get_student("sara_cs")
_, zain  = get_student("zain_se")
_, nida  = get_student("nida_cs")

ali_id  = ali["_id"]
sara_id = sara["_id"]
zain_id = zain["_id"]
nida_id = nida["_id"]

# course shortcuts
CS301 = get_course("CS301")["_id"]
CS302 = get_course("CS302")["_id"]
CS303 = get_course("CS303")["_id"]
CS304 = get_course("CS304")["_id"]
CS201 = get_course("CS201")["_id"]
CS202 = get_course("CS202")["_id"]
CS203 = get_course("CS203")["_id"]
CS204 = get_course("CS204")["_id"]
SE501 = get_course("SE501")["_id"]
SE502 = get_course("SE502")["_id"]
SE503 = get_course("SE503")["_id"]
SE504 = get_course("SE504")["_id"]

def days_ago(n):    return datetime.now() - timedelta(days=n)
def days_from(n):   return datetime.now() + timedelta(days=n)

# ─────────────────────────────────────────
# DROP ADDITIONAL COLLECTIONS (fresh seed)
# ─────────────────────────────────────────
extra_cols = [
    "attendance", "timetable", "semester_results",
    "announcements", "library", "complaints", "scholarships"
]
for col in extra_cols:
    db[col].drop()
print("🗑️   Dropped existing additional collections.\n")


# ══════════════════════════════════════════
# 1. ATTENDANCE
# ══════════════════════════════════════════
print("📋  Seeding attendance...")

def make_attendance(student_id, course_id, total, attended):
    pct = round((attended / total) * 100, 1)
    return {
        "student_id"     : student_id,
        "course_id"      : course_id,
        "university"     : UNIVERSITY,
        "total_classes"  : total,
        "attended"       : attended,
        "absent"         : total - attended,
        "percentage"     : pct,
        "status"         : "good" if pct >= 75 else "warning" if pct >= 60 else "critical",
        "last_updated"   : days_ago(1),
        "semester"       : 3,
        "session_year"   : "2024-25",
    }

attendance_records = [
    # Ali — 3rd sem CS (has one critical subject to trigger warning)
    make_attendance(ali_id, CS301, 30, 22),   # 73% — warning
    make_attendance(ali_id, CS302, 28, 26),   # 92% — good
    make_attendance(ali_id, CS303, 32, 18),   # 56% — critical ← shortage
    make_attendance(ali_id, CS304, 30, 24),   # 80% — good

    # Sara — 3rd sem CS (all good)
    make_attendance(sara_id, CS301, 30, 29),  # 96%
    make_attendance(sara_id, CS302, 28, 27),  # 96%
    make_attendance(sara_id, CS303, 32, 31),  # 96%
    make_attendance(sara_id, CS304, 30, 28),  # 93%

    # Zain — 5th sem SE
    make_attendance(zain_id, SE501, 30, 25),  # 83%
    make_attendance(zain_id, SE502, 28, 20),  # 71% — warning
    make_attendance(zain_id, SE503, 30, 28),  # 93%
    make_attendance(zain_id, SE504, 32, 22),  # 68% — warning

    # Nida — 2nd sem CS
    make_attendance(nida_id, CS201, 28, 27),  # 96%
    make_attendance(nida_id, CS202, 30, 29),  # 96%
    make_attendance(nida_id, CS203, 28, 25),  # 89%
    make_attendance(nida_id, CS204, 30, 24),  # 80%
]

db["attendance"].insert_many(attendance_records)
db["attendance"].create_index([("student_id", 1), ("course_id", 1)], unique=True)
print(f"   ✅  {len(attendance_records)} attendance records inserted.\n")


# ══════════════════════════════════════════
# 2. TIMETABLE
# ══════════════════════════════════════════
print("🕐  Seeding timetable...")

# days: 1=Monday ... 5=Friday
timetable = [

    # ── 3rd Semester CS (Ali & Sara) ──
    {"course_id": CS301, "course_code": "CS301", "course_name": "Advanced NLP",
     "day": "Monday",    "day_num": 1, "start": "08:00", "end": "09:30",
     "room": "CS-Lab 2", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS302, "course_code": "CS302", "course_name": "Database Systems",
     "day": "Monday",    "day_num": 1, "start": "10:00", "end": "11:30",
     "room": "Room 204", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS303, "course_code": "CS303", "course_name": "Operating Systems",
     "day": "Tuesday",   "day_num": 2, "start": "08:00", "end": "09:30",
     "room": "Room 101", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS304, "course_code": "CS304", "course_name": "Software Engineering",
     "day": "Tuesday",   "day_num": 2, "start": "11:00", "end": "12:30",
     "room": "Room 205", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS301, "course_code": "CS301", "course_name": "Advanced NLP",
     "day": "Wednesday", "day_num": 3, "start": "08:00", "end": "09:30",
     "room": "CS-Lab 2", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS302, "course_code": "CS302", "course_name": "Database Systems",
     "day": "Wednesday", "day_num": 3, "start": "10:00", "end": "11:30",
     "room": "Room 204", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS303, "course_code": "CS303", "course_name": "Operating Systems",
     "day": "Thursday",  "day_num": 4, "start": "08:00", "end": "09:30",
     "room": "Room 101", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS304, "course_code": "CS304", "course_name": "Software Engineering",
     "day": "Thursday",  "day_num": 4, "start": "11:00", "end": "12:30",
     "room": "Room 205", "semester": 3, "department": "CS", "session": "2024-25"},

    {"course_id": CS301, "course_code": "CS301", "course_name": "Advanced NLP",
     "day": "Friday",    "day_num": 5, "start": "09:00", "end": "10:30",
     "room": "CS-Lab 2", "semester": 3, "department": "CS", "session": "2024-25"},

    # ── 5th Semester SE (Zain) ──
    {"course_id": SE501, "course_code": "SE501", "course_name": "Software Architecture",
     "day": "Monday",    "day_num": 1, "start": "09:00", "end": "10:30",
     "room": "Room 301", "semester": 5, "department": "SE", "session": "2024-25"},

    {"course_id": SE502, "course_code": "SE502", "course_name": "Mobile App Development",
     "day": "Monday",    "day_num": 1, "start": "11:00", "end": "12:30",
     "room": "SE-Lab 1", "semester": 5, "department": "SE", "session": "2024-25"},

    {"course_id": SE503, "course_code": "SE503", "course_name": "Cloud Computing",
     "day": "Tuesday",   "day_num": 2, "start": "09:00", "end": "10:30",
     "room": "Room 302", "semester": 5, "department": "SE", "session": "2024-25"},

    {"course_id": SE504, "course_code": "SE504", "course_name": "DevOps & CI/CD",
     "day": "Wednesday", "day_num": 3, "start": "11:00", "end": "12:30",
     "room": "SE-Lab 2", "semester": 5, "department": "SE", "session": "2024-25"},

    {"course_id": SE501, "course_code": "SE501", "course_name": "Software Architecture",
     "day": "Thursday",  "day_num": 4, "start": "09:00", "end": "10:30",
     "room": "Room 301", "semester": 5, "department": "SE", "session": "2024-25"},

    {"course_id": SE502, "course_code": "SE502", "course_name": "Mobile App Development",
     "day": "Friday",    "day_num": 5, "start": "10:00", "end": "11:30",
     "room": "SE-Lab 1", "semester": 5, "department": "SE", "session": "2024-25"},

    # ── 2nd Semester CS (Nida) ──
    {"course_id": CS201, "course_code": "CS201", "course_name": "Object Oriented Programming",
     "day": "Monday",    "day_num": 1, "start": "08:00", "end": "09:30",
     "room": "CS-Lab 1", "semester": 2, "department": "CS", "session": "2024-25"},

    {"course_id": CS202, "course_code": "CS202", "course_name": "Data Structures",
     "day": "Tuesday",   "day_num": 2, "start": "10:00", "end": "11:30",
     "room": "Room 102", "semester": 2, "department": "CS", "session": "2024-25"},

    {"course_id": CS203, "course_code": "CS203", "course_name": "Linear Algebra",
     "day": "Wednesday", "day_num": 3, "start": "08:00", "end": "09:30",
     "room": "Room 103", "semester": 2, "department": "CS", "session": "2024-25"},

    {"course_id": CS204, "course_code": "CS204", "course_name": "Computer Organization",
     "day": "Thursday",  "day_num": 4, "start": "10:00", "end": "11:30",
     "room": "Room 104", "semester": 2, "department": "CS", "session": "2024-25"},

    {"course_id": CS202, "course_code": "CS202", "course_name": "Data Structures",
     "day": "Friday",    "day_num": 5, "start": "08:00", "end": "09:30",
     "room": "CS-Lab 1", "semester": 2, "department": "CS", "session": "2024-25"},
]

for t in timetable:
    t["university"] = UNIVERSITY

db["timetable"].insert_many(timetable)
db["timetable"].create_index([("semester", 1), ("department", 1), ("day_num", 1)])
print(f"   ✅  {len(timetable)} timetable slots inserted.\n")


# ══════════════════════════════════════════
# 3. SEMESTER RESULTS (CGPA history)
# ══════════════════════════════════════════
print("📊  Seeding semester results...")

semester_results = [

    # ── Ali ──
    {"student_id": ali_id, "semester": 1, "sgpa": 3.45, "cgpa": 3.45,
     "total_credit_hours": 11, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2023-24", "university": UNIVERSITY},

    {"student_id": ali_id, "semester": 2, "sgpa": 3.10, "cgpa": 3.28,
     "total_credit_hours": 23, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2023-24", "university": UNIVERSITY},

    # ── Sara ──
    {"student_id": sara_id, "semester": 1, "sgpa": 3.85, "cgpa": 3.85,
     "total_credit_hours": 11, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2023-24", "university": UNIVERSITY},

    {"student_id": sara_id, "semester": 2, "sgpa": 3.72, "cgpa": 3.79,
     "total_credit_hours": 23, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2023-24", "university": UNIVERSITY},

    # ── Zain ──
    {"student_id": zain_id, "semester": 1, "sgpa": 3.20, "cgpa": 3.20,
     "total_credit_hours": 11, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2022-23", "university": UNIVERSITY},

    {"student_id": zain_id, "semester": 2, "sgpa": 2.90, "cgpa": 3.05,
     "total_credit_hours": 23, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2022-23", "university": UNIVERSITY},

    {"student_id": zain_id, "semester": 3, "sgpa": 3.00, "cgpa": 3.03,
     "total_credit_hours": 35, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2023-24", "university": UNIVERSITY},

    {"student_id": zain_id, "semester": 4, "sgpa": 2.75, "cgpa": 2.96,
     "total_credit_hours": 47, "passed": 3, "failed": 1,
     "result_status": "probation", "session_year": "2023-24", "university": UNIVERSITY},

    # ── Nida ──
    {"student_id": nida_id, "semester": 1, "sgpa": 3.60, "cgpa": 3.60,
     "total_credit_hours": 11, "passed": 4, "failed": 0,
     "result_status": "pass", "session_year": "2024-25", "university": UNIVERSITY},
]

db["semester_results"].insert_many(semester_results)
db["semester_results"].create_index([("student_id", 1), ("semester", 1)], unique=True)
print(f"   ✅  {len(semester_results)} semester result records inserted.\n")


# ══════════════════════════════════════════
# 4. ANNOUNCEMENTS
# ══════════════════════════════════════════
print("📢  Seeding announcements...")

announcements = [
    {
        "university"  : UNIVERSITY,
        "title"       : "Mid-Term Exam Schedule Released",
        "body"        : "The mid-term examination schedule for Spring 2025 has been released. "
                        "All students are advised to check their exam dates on the portal. "
                        "Exams will begin in 12 days. Hall tickets must be collected from the admin office.",
        "category"    : "exam",
        "target"      : "all",
        "departments" : ["CS", "SE", "BBA", "MBA"],
        "semesters"   : [],
        "posted_by"   : "Examination Department, IBA Sukkur",
        "posted_at"   : days_ago(2),
        "is_urgent"   : True,
        "is_active"   : True,
    },
    {
        "university"  : UNIVERSITY,
        "title"       : "Fee Submission Last Date — 30th April 2025",
        "body"        : "This is a reminder that the last date for fee submission for Spring 2025 semester "
                        "is 30th April 2025. Students who fail to pay fees by the due date will not be "
                        "allowed to appear in mid-term examinations. Pay via HBL or Bank Alfalah challan.",
        "category"    : "fee",
        "target"      : "all",
        "departments" : ["CS", "SE", "BBA", "MBA"],
        "semesters"   : [],
        "posted_by"   : "Accounts Department, IBA Sukkur",
        "posted_at"   : days_ago(5),
        "is_urgent"   : True,
        "is_active"   : True,
    },
    {
        "university"  : UNIVERSITY,
        "title"       : "CS Department Seminar — AI in Healthcare",
        "body"        : "The Department of Computer Science is organizing a seminar on "
                        "'Artificial Intelligence Applications in Healthcare' on 28th April 2025 "
                        "at 10:00 AM in the Main Auditorium. All CS and SE students are encouraged to attend. "
                        "Certificates of participation will be awarded.",
        "category"    : "event",
        "target"      : "department",
        "departments" : ["CS", "SE"],
        "semesters"   : [],
        "posted_by"   : "CS Department, IBA Sukkur",
        "posted_at"   : days_ago(3),
        "is_urgent"   : False,
        "is_active"   : True,
    },
    {
        "university"  : UNIVERSITY,
        "title"       : "Library Card Renewal — Spring 2025",
        "body"        : "All students are required to renew their library cards for Spring 2025. "
                        "Visit the library office with your university ID card between 9 AM – 1 PM. "
                        "Students with overdue books must return them before renewal.",
        "category"    : "library",
        "target"      : "all",
        "departments" : [],
        "semesters"   : [],
        "posted_by"   : "Library, IBA Sukkur",
        "posted_at"   : days_ago(7),
        "is_urgent"   : False,
        "is_active"   : True,
    },
    {
        "university"  : UNIVERSITY,
        "title"       : "Attendance Warning — 3rd Semester CS",
        "body"        : "Several students of 3rd Semester CS have attendance below 75% in one or more subjects. "
                        "Students are reminded that a minimum of 75% attendance is mandatory to appear in exams. "
                        "Students with critical shortage must contact their respective course teachers immediately.",
        "category"    : "attendance",
        "target"      : "semester",
        "departments" : ["CS"],
        "semesters"   : [3],
        "posted_by"   : "Academic Office, IBA Sukkur",
        "posted_at"   : days_ago(1),
        "is_urgent"   : True,
        "is_active"   : True,
    },
    {
        "university"  : UNIVERSITY,
        "title"       : "Public Holiday — 23rd March Pakistan Day",
        "body"        : "The university will remain closed on Sunday 23rd March on account of Pakistan Day. "
                        "All classes and activities scheduled for that day stand cancelled.",
        "category"    : "holiday",
        "target"      : "all",
        "departments" : [],
        "semesters"   : [],
        "posted_by"   : "Administration, IBA Sukkur",
        "posted_at"   : days_ago(14),
        "is_urgent"   : False,
        "is_active"   : False,   # past event
    },
    {
        "university"  : UNIVERSITY,
        "title"       : "HEC Scholarship Applications Open",
        "body"        : "Applications for HEC Need-Based Scholarships for Spring 2025 are now open. "
                        "Eligible students (CGPA 2.5+, family income below PKR 45,000/month) can apply "
                        "through the student portal. Last date to apply: 10th May 2025.",
        "category"    : "scholarship",
        "target"      : "all",
        "departments" : [],
        "semesters"   : [],
        "posted_by"   : "Student Affairs, IBA Sukkur",
        "posted_at"   : days_ago(4),
        "is_urgent"   : False,
        "is_active"   : True,
    },
    {
        "university"  : UNIVERSITY,
        "title"       : "Revised Academic Calendar — Spring 2025",
        "body"        : "The Academic Calendar for Spring 2025 has been revised. "
                        "Mid-term exams: 5th May – 12th May. Final exams: 25th June – 5th July. "
                        "Result declaration: 20th July. Please plan accordingly.",
        "category"    : "academic",
        "target"      : "all",
        "departments" : [],
        "semesters"   : [],
        "posted_by"   : "Registrar Office, IBA Sukkur",
        "posted_at"   : days_ago(10),
        "is_urgent"   : False,
        "is_active"   : True,
    },
]

db["announcements"].insert_many(announcements)
db["announcements"].create_index([("is_active", 1), ("posted_at", -1)])
print(f"   ✅  {len(announcements)} announcements inserted.\n")


# ══════════════════════════════════════════
# 5. LIBRARY
# ══════════════════════════════════════════
print("📚  Seeding library records...")

library_records = [
    # Ali
    {"student_id": ali_id,  "university": UNIVERSITY,
     "book_title": "Introduction to Machine Learning",  "author": "Alpaydin",
     "isbn": "978-0262043793", "issued_date": days_ago(20),
     "due_date": days_ago(6),  "return_date": None,
     "status": "overdue",      "fine_per_day": 10,
     "fine_amount": 60,        "fine_paid": False},

    {"student_id": ali_id,  "university": UNIVERSITY,
     "book_title": "Operating System Concepts",         "author": "Silberschatz",
     "isbn": "978-1119800361", "issued_date": days_ago(10),
     "due_date": days_from(4), "return_date": None,
     "status": "issued",       "fine_per_day": 10,
     "fine_amount": 0,         "fine_paid": False},

    # Sara
    {"student_id": sara_id, "university": UNIVERSITY,
     "book_title": "Speech and Language Processing",    "author": "Jurafsky & Martin",
     "isbn": "978-0131873216", "issued_date": days_ago(15),
     "due_date": days_from(6), "return_date": None,
     "status": "issued",       "fine_per_day": 10,
     "fine_amount": 0,         "fine_paid": False},

    {"student_id": sara_id, "university": UNIVERSITY,
     "book_title": "Database System Concepts",          "author": "Silberschatz",
     "isbn": "978-0073523323", "issued_date": days_ago(30),
     "due_date": days_ago(2),  "return_date": days_ago(1),
     "status": "returned",     "fine_per_day": 10,
     "fine_amount": 0,         "fine_paid": False},

    # Zain
    {"student_id": zain_id, "university": UNIVERSITY,
     "book_title": "Clean Architecture",                "author": "Robert C. Martin",
     "isbn": "978-0134494166", "issued_date": days_ago(12),
     "due_date": days_from(2), "return_date": None,
     "status": "issued",       "fine_per_day": 10,
     "fine_amount": 0,         "fine_paid": False},

    {"student_id": zain_id, "university": UNIVERSITY,
     "book_title": "Docker Deep Dive",                  "author": "Nigel Poulton",
     "isbn": "978-1521822807", "issued_date": days_ago(25),
     "due_date": days_ago(4),  "return_date": None,
     "status": "overdue",      "fine_per_day": 10,
     "fine_amount": 40,        "fine_paid": False},

    # Nida
    {"student_id": nida_id, "university": UNIVERSITY,
     "book_title": "Head First Java",                   "author": "Kathy Sierra",
     "isbn": "978-0596009205", "issued_date": days_ago(8),
     "due_date": days_from(6), "return_date": None,
     "status": "issued",       "fine_per_day": 10,
     "fine_amount": 0,         "fine_paid": False},
]

db["library"].insert_many(library_records)
db["library"].create_index([("student_id", 1), ("status", 1)])
print(f"   ✅  {len(library_records)} library records inserted.\n")


# ══════════════════════════════════════════
# 6. COMPLAINTS & REQUESTS
# ══════════════════════════════════════════
print("📨  Seeding complaints and requests...")

complaints = [
    # Ali
    {
        "student_id"  : ali_id,
        "university"  : UNIVERSITY,
        "type"        : "transcript_request",
        "subject"     : "Official Transcript Required for Internship Application",
        "description" : "I need an official transcript for my internship application at TechCorp. "
                        "Please issue it as soon as possible.",
        "status"      : "on_hold",
        "hold_reason" : "Fee dues unpaid. Transcript will be issued after fee clearance.",
        "submitted_at": days_ago(5),
        "resolved_at" : None,
        "response"    : "Your request is on hold due to pending fee dues of PKR 48,000. "
                        "Please clear your dues and resubmit the request.",
        "ticket_no"   : "TKT-2025-0041",
    },
    {
        "student_id"  : ali_id,
        "university"  : UNIVERSITY,
        "type"        : "complaint",
        "subject"     : "Attendance Marked Wrong in OS Subject",
        "description" : "I was present in the OS class on 15th April but was marked absent. "
                        "Please correct my attendance record.",
        "status"      : "in_progress",
        "hold_reason" : None,
        "submitted_at": days_ago(3),
        "resolved_at" : None,
        "response"    : "Your complaint has been forwarded to the OS course teacher for verification.",
        "ticket_no"   : "TKT-2025-0048",
    },

    # Sara
    {
        "student_id"  : sara_id,
        "university"  : UNIVERSITY,
        "type"        : "transcript_request",
        "subject"     : "Transcript for Higher Studies Application",
        "description" : "I am applying for MS admission and need an official transcript.",
        "status"      : "resolved",
        "hold_reason" : None,
        "submitted_at": days_ago(10),
        "resolved_at" : days_ago(7),
        "response"    : "Your official transcript has been prepared and is ready for collection "
                        "from the Registrar Office. Please bring your university ID.",
        "ticket_no"   : "TKT-2025-0031",
    },
    {
        "student_id"  : sara_id,
        "university"  : UNIVERSITY,
        "type"        : "query",
        "subject"     : "Grading Criteria for NLP Course",
        "description" : "Can you please clarify the grading breakdown for CS301?",
        "status"      : "resolved",
        "hold_reason" : None,
        "submitted_at": days_ago(15),
        "resolved_at" : days_ago(13),
        "response"    : "Mid-term 25%, Assignments 25%, Final 50%. Please refer to course outline.",
        "ticket_no"   : "TKT-2025-0018",
    },

    # Zain
    {
        "student_id"  : zain_id,
        "university"  : UNIVERSITY,
        "type"        : "enrollment_certificate",
        "subject"     : "Enrollment Certificate for Bank Account",
        "description" : "I need an enrollment certificate to open a student bank account at HBL.",
        "status"      : "on_hold",
        "hold_reason" : "Partial fee dues pending.",
        "submitted_at": days_ago(4),
        "resolved_at" : None,
        "response"    : "Your request is on hold. Please clear the remaining fee balance of PKR 23,000.",
        "ticket_no"   : "TKT-2025-0052",
    },

    # Nida
    {
        "student_id"  : nida_id,
        "university"  : UNIVERSITY,
        "type"        : "complaint",
        "subject"     : "AC Not Working in Room 102",
        "description" : "The air conditioning in Room 102 has not been working for the past week. "
                        "It is very difficult to sit through 2-hour classes in extreme heat.",
        "status"      : "resolved",
        "hold_reason" : None,
        "submitted_at": days_ago(6),
        "resolved_at" : days_ago(2),
        "response"    : "The maintenance team has repaired the AC in Room 102. Issue is resolved.",
        "ticket_no"   : "TKT-2025-0039",
    },
]

db["complaints"].insert_many(complaints)
db["complaints"].create_index([("student_id", 1), ("status", 1)])
print(f"   ✅  {len(complaints)} complaint/request records inserted.\n")


# ══════════════════════════════════════════
# 7. SCHOLARSHIPS
# ══════════════════════════════════════════
print("🎓  Seeding scholarships...")

scholarships = [
    # Sara — active HEC scholarship (all paid, high CGPA)
    {
        "student_id"        : sara_id,
        "university"        : UNIVERSITY,
        "scholarship_name"  : "HEC Need-Based Scholarship",
        "provider"          : "Higher Education Commission Pakistan",
        "amount_per_semester": 24000,
        "total_awarded"     : 48000,
        "total_disbursed"   : 48000,
        "status"            : "active",
        "start_semester"    : 1,
        "end_semester"      : 8,
        "current_semester"  : 3,
        "next_disbursement" : days_from(20),
        "last_disbursement" : days_ago(120),
        "cgpa_requirement"  : 2.5,
        "remarks"           : "Renewable every semester with CGPA >= 2.5",
        "applied_at"        : days_ago(400),
        "approved_at"       : days_ago(380),
    },

    # Nida — IBA merit scholarship
    {
        "student_id"        : nida_id,
        "university"        : UNIVERSITY,
        "scholarship_name"  : "IBA Sukkur Merit Scholarship",
        "provider"          : "IBA Sukkur",
        "amount_per_semester": 35000,
        "total_awarded"     : 35000,
        "total_disbursed"   : 35000,
        "status"            : "active",
        "start_semester"    : 1,
        "end_semester"      : 8,
        "current_semester"  : 2,
        "next_disbursement" : days_from(30),
        "last_disbursement" : days_ago(90),
        "cgpa_requirement"  : 3.5,
        "remarks"           : "Awarded to top 5% students. Renewable with CGPA >= 3.5",
        "applied_at"        : days_ago(370),
        "approved_at"       : days_ago(360),
    },

    # Ali — applied but not approved (unpaid fees, lower CGPA)
    {
        "student_id"        : ali_id,
        "university"        : UNIVERSITY,
        "scholarship_name"  : "HEC Need-Based Scholarship",
        "provider"          : "Higher Education Commission Pakistan",
        "amount_per_semester": 24000,
        "total_awarded"     : 0,
        "total_disbursed"   : 0,
        "status"            : "applied",
        "start_semester"    : 3,
        "end_semester"      : None,
        "current_semester"  : 3,
        "next_disbursement" : None,
        "last_disbursement" : None,
        "cgpa_requirement"  : 2.5,
        "remarks"           : "Application under review. Fee clearance required.",
        "applied_at"        : days_ago(10),
        "approved_at"       : None,
    },

    # Zain — expired scholarship (was on probation)
    {
        "student_id"        : zain_id,
        "university"        : UNIVERSITY,
        "scholarship_name"  : "Sindh Government Scholarship",
        "provider"          : "Government of Sindh",
        "amount_per_semester": 20000,
        "total_awarded"     : 80000,
        "total_disbursed"   : 80000,
        "status"            : "expired",
        "start_semester"    : 1,
        "end_semester"      : 4,
        "current_semester"  : 5,
        "next_disbursement" : None,
        "last_disbursement" : days_ago(160),
        "cgpa_requirement"  : 2.75,
        "remarks"           : "Expired. CGPA dropped below requirement in semester 4.",
        "applied_at"        : days_ago(740),
        "approved_at"       : days_ago(720),
    },
]

db["scholarships"].insert_many(scholarships)
db["scholarships"].create_index([("student_id", 1), ("status", 1)])
print(f"   ✅  {len(scholarships)} scholarship records inserted.\n")


# ══════════════════════════════════════════
# INDEXES
# ══════════════════════════════════════════
print("🔍  Creating indexes...")
db["announcements"].create_index([("category", 1), ("target", 1)])
db["library"].create_index([("student_id", 1), ("due_date", 1)])
db["complaints"].create_index([("student_id", 1), ("type", 1)])
db["scholarships"].create_index([("student_id", 1)])
print("   ✅  Indexes created.\n")


# ══════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════
print("=" * 55)
print(f"✅  ADDITIONAL SEED COMPLETE — {UNIVERSITY}")
print("=" * 55)
print(f"""
📦  Database  : {DB_NAME}
🏫  University: {UNIVERSITY}

📊  Collections Added:
   attendance          → {db['attendance'].count_documents({})} records
   timetable           → {db['timetable'].count_documents({})} slots
   semester_results    → {db['semester_results'].count_documents({})} records
   announcements       → {db['announcements'].count_documents({})} notices
   library             → {db['library'].count_documents({})} book records
   complaints          → {db['complaints'].count_documents({})} tickets
   scholarships        → {db['scholarships'].count_documents({})} records

🧪  TEST SCENARIOS READY:
┌────────────┬──────────────────────────────────────────────────┐
│ ali_cs     │ Attendance shortage in OS (56%)                  │
│            │ Overdue library book + fine PKR 60               │
│            │ Transcript request ON HOLD (fee unpaid)          │
│            │ Scholarship application pending                  │
├────────────┼──────────────────────────────────────────────────┤
│ sara_cs    │ All attendance good                              │
│            │ Active HEC scholarship (next disbursement soon)  │
│            │ Transcript request resolved                      │
├────────────┼──────────────────────────────────────────────────┤
│ zain_se    │ 2 subjects attendance warning                    │
│            │ Overdue library book + fine PKR 40               │
│            │ Enrollment cert ON HOLD (partial fee)            │
│            │ Scholarship expired (probation)                  │
├────────────┼──────────────────────────────────────────────────┤
│ nida_cs    │ All clean, merit scholarship active              │
│            │ AC complaint resolved                            │
└────────────┴──────────────────────────────────────────────────┘

💬  SAMPLE CHATBOT QUERIES TO TEST:
   "meri attendance kitni hai?"
   "kal meri kaunsi classes hain?"
   "koi naya notice hai?"
   "meri issued books kaun si hain?"
   "meri scholarship ka status kya hai?"
   "mera overall CGPA kya hai?"
   "meri complaint ka kya hua?"
   "OS mein meri attendance low kyun hai?"
""")

client.close()