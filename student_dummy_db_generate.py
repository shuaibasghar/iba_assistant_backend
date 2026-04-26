"""
IBA Sukkur University Portal - MongoDB Seed Script
---------------------------------------------------
Run: python dummy_db_generate.py
Requires: pip install pymongo bcrypt faker
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
from bson import ObjectId
import bcrypt
import random

# ─────────────────────────────────────────
# CONFIG — change MONGO_URI if needed
# ─────────────────────────────────────────
MONGO_URI = "mongodb://localhost:27017"
DB_NAME   = "iba_suk_portal"

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def random_date(start_days_ago: int, end_days_ago: int) -> datetime:
    delta = random.randint(end_days_ago, start_days_ago)
    return datetime.now() - timedelta(days=delta)

def future_date(days_from_now: int) -> datetime:
    return datetime.now() + timedelta(days=days_from_now)

# ─────────────────────────────────────────
# WIPE EXISTING DATA
# ─────────────────────────────────────────
print("🗑️  Dropping existing collections...")
collections = [
    "users", "students", "courses", "enrollments",
    "assignments", "assignment_submissions",
    "grades", "exams", "fees", "chat_logs"
]
for col in collections:
    db[col].drop()
print("✅  Collections cleared.\n")

# ─────────────────────────────────────────
# 1. COURSES
# ─────────────────────────────────────────
print("📚  Seeding courses...")

courses_data = [
    # 1st semester CS
    {"course_code": "CS101", "course_name": "Introduction to Programming",    "credit_hours": 3, "semester": 1, "department": "CS"},
    {"course_code": "CS102", "course_name": "Discrete Mathematics",           "credit_hours": 3, "semester": 1, "department": "CS"},
    {"course_code": "CS103", "course_name": "Digital Logic Design",           "credit_hours": 3, "semester": 1, "department": "CS"},
    {"course_code": "ENG101","course_name": "English Communication",          "credit_hours": 2, "semester": 1, "department": "CS"},

    # 2nd semester CS
    {"course_code": "CS201", "course_name": "Object Oriented Programming",    "credit_hours": 3, "semester": 2, "department": "CS"},
    {"course_code": "CS202", "course_name": "Data Structures",                "credit_hours": 3, "semester": 2, "department": "CS"},
    {"course_code": "CS203", "course_name": "Linear Algebra",                 "credit_hours": 3, "semester": 2, "department": "CS"},
    {"course_code": "CS204", "course_name": "Computer Organization",          "credit_hours": 3, "semester": 2, "department": "CS"},

    # 3rd semester CS  ← our main test students are here
    {"course_code": "CS301", "course_name": "Advanced Natural Language Processing", "credit_hours": 3, "semester": 3, "department": "CS"},
    {"course_code": "CS302", "course_name": "Database Systems",               "credit_hours": 3, "semester": 3, "department": "CS"},
    {"course_code": "CS303", "course_name": "Operating Systems",              "credit_hours": 3, "semester": 3, "department": "CS"},
    {"course_code": "CS304", "course_name": "Software Engineering",           "credit_hours": 3, "semester": 3, "department": "CS"},

    # 5th semester SE
    {"course_code": "SE501", "course_name": "Software Architecture",         "credit_hours": 3, "semester": 5, "department": "SE"},
    {"course_code": "SE502", "course_name": "Mobile Application Development","credit_hours": 3, "semester": 5, "department": "SE"},
    {"course_code": "SE503", "course_name": "Cloud Computing",               "credit_hours": 3, "semester": 5, "department": "SE"},
    {"course_code": "SE504", "course_name": "DevOps & CI/CD",                "credit_hours": 3, "semester": 5, "department": "SE"},
]

result   = db["courses"].insert_many(courses_data)
course_ids = result.inserted_ids

# Map course_code → ObjectId for easy reference
course_map = {c["course_code"]: course_ids[i] for i, c in enumerate(courses_data)}
print(f"   ✅  {len(course_ids)} courses inserted.\n")

# ─────────────────────────────────────────
# 2. USERS + STUDENTS
# ─────────────────────────────────────────
print("👤  Seeding users and students...")

students_raw = [
    # ── Student 1: Ali (3rd sem CS, FEES UNPAID) ──
    {
        "username"    : "ali_cs",
        "email"       : "ali.khan@iba-suk.edu.pk",
        "password"    : "student123",
        "role"        : "student",
        "full_name"   : "Ali Khan",
        "roll_number" : "CS-2023-001",
        "semester"    : 3,
        "department"  : "CS",
        "batch"       : "2023",
        "dob"         : datetime(2002, 5, 14),
        "phone"       : "0300-1234567",
        "address"     : "House 12, Airport Road, Sukkur",
        "fee_status"  : "unpaid",
        "courses"     : ["CS301","CS302","CS303","CS304"],
    },
    # ── Student 2: Sara (3rd sem CS, FEES PAID) ──
    {
        "username"    : "sara_cs",
        "email"       : "sara.ali@iba-suk.edu.pk",
        "password"    : "student123",
        "role"        : "student",
        "full_name"   : "Sara Ali",
        "roll_number" : "CS-2023-002",
        "semester"    : 3,
        "department"  : "CS",
        "batch"       : "2023",
        "dob"         : datetime(2002, 9, 22),
        "phone"       : "0333-9876543",
        "address"     : "House 45, Military Road, Sukkur",
        "fee_status"  : "paid",
        "courses"     : ["CS301","CS302","CS303","CS304"],
    },
    # ── Student 3: Zain (5th sem SE, FEES PARTIAL) ──
    {
        "username"    : "zain_se",
        "email"       : "zain.malik@iba-suk.edu.pk",
        "password"    : "student123",
        "role"        : "student",
        "full_name"   : "Zain Malik",
        "roll_number" : "SE-2022-011",
        "semester"    : 5,
        "department"  : "SE",
        "batch"       : "2022",
        "dob"         : datetime(2001, 3, 7),
        "phone"       : "0321-5554321",
        "address"     : "Flat 8, Barrage Colony, Sukkur",
        "fee_status"  : "partial",
        "courses"     : ["SE501","SE502","SE503","SE504"],
    },
    # ── Student 4: Nida (2nd sem CS, FEES PAID) ──
    {
        "username"    : "nida_cs",
        "email"       : "nida.hussain@iba-suk.edu.pk",
        "password"    : "student123",
        "role"        : "student",
        "full_name"   : "Nida Hussain",
        "roll_number" : "CS-2024-007",
        "semester"    : 2,
        "department"  : "CS",
        "batch"       : "2024",
        "dob"         : datetime(2003, 11, 30),
        "phone"       : "0345-7654321",
        "address"     : "House 23, Minara Road, Sukkur",
        "fee_status"  : "paid",
        "courses"     : ["CS201","CS202","CS203","CS204"],
    },
]

user_ids    = {}
student_ids = {}

for s in students_raw:
    # Insert into users collection
    user_doc = {
        "username"      : s["username"],
        "email"         : s["email"],
        "password_hash" : hash_password(s["password"]),
        "role"          : s["role"],
        "is_active"     : True,
        "created_at"    : datetime.now(),
        "last_login"    : None,
    }
    user_id = db["users"].insert_one(user_doc).inserted_id
    user_ids[s["username"]] = user_id

    # Insert into students collection
    student_doc = {
        "user_id"     : user_id,
        "full_name"   : s["full_name"],
        "roll_number" : s["roll_number"],
        "email"       : s["email"],
        "semester"    : s["semester"],
        "department"  : s["department"],
        "batch"       : s["batch"],
        "dob"         : s["dob"],
        "phone"       : s["phone"],
        "address"     : s["address"],
        "cgpa"        : round(random.uniform(2.8, 3.9), 2),
        "status"      : "active",
        "created_at"  : datetime.now(),
    }
    student_id = db["students"].insert_one(student_doc).inserted_id
    student_ids[s["username"]] = student_id

    # Update user with student_id ref
    db["users"].update_one(
        {"_id": user_id},
        {"$set": {"student_id": student_id}}
    )

# ── Superadmin (JWT role `superadmin`; legacy seeds used `superuser`) ──
super_user = {
    "username": "superadmin",
    "email": "admin@iba-suk.edu.pk",
    "password_hash": hash_password("admin123"),
    "role": "superadmin",
    "is_active": True,
    "created_at": datetime.now(),
    "last_login": None,
    "student_id": None,
}
sa_uid = db["users"].insert_one(super_user).inserted_id
db["superadmins"].insert_one({
    "user_id": sa_uid,
    "full_name": "System Superadmin",
    "email": "admin@iba-suk.edu.pk",
    "employee_id": "SUP-001",
    "department": "System",
    "password_hash": super_user["password_hash"],
    "designation": "Superadmin",
    "role": "superadmin",
    "status": "active",
    "created_at": datetime.now(),
})

print(f"   ✅  {len(students_raw)} students + 1 superadmin inserted.\n")

# ─────────────────────────────────────────
# 3. ENROLLMENTS
# ─────────────────────────────────────────
print("📋  Seeding enrollments...")

enrollments = []
for s in students_raw:
    for code in s["courses"]:
        enrollments.append({
            "student_id"   : student_ids[s["username"]],
            "course_id"    : course_map[code],
            "session_year" : "2024-25",
            "semester"     : s["semester"],
            "enrolled_at"  : random_date(90, 85),
        })

db["enrollments"].insert_many(enrollments)
print(f"   ✅  {len(enrollments)} enrollments inserted.\n")

# ─────────────────────────────────────────
# 4. ASSIGNMENTS
# ─────────────────────────────────────────
print("📝  Seeding assignments...")

assignments_data = []

# CS 3rd semester assignments
cs3_assignments = [
    # NLP — CS301
    {"course_code": "CS301", "title": "Text Preprocessing Pipeline",       "due_offset": -10, "total_marks": 20},
    {"course_code": "CS301", "title": "TF-IDF vs Word2Vec Comparison",     "due_offset": 5,   "total_marks": 25},
    {"course_code": "CS301", "title": "Fine-tuning BERT on Custom Dataset","due_offset": 15,  "total_marks": 30},

    # DB — CS302
    {"course_code": "CS302", "title": "ER Diagram Design",                 "due_offset": -5,  "total_marks": 20},
    {"course_code": "CS302", "title": "SQL Query Optimization Lab",        "due_offset": 7,   "total_marks": 20},

    # OS — CS303
    {"course_code": "CS303", "title": "Process Scheduling Simulation",    "due_offset": -15, "total_marks": 25},
    {"course_code": "CS303", "title": "Memory Management Report",          "due_offset": 10,  "total_marks": 20},

    # SE — CS304
    {"course_code": "CS304", "title": "SRS Document Preparation",         "due_offset": -3,  "total_marks": 30},
    {"course_code": "CS304", "title": "UML Diagrams Assignment",           "due_offset": 12,  "total_marks": 25},
]

# SE 5th semester assignments
se5_assignments = [
    {"course_code": "SE501", "title": "Microservices Architecture Design", "due_offset": -7,  "total_marks": 30},
    {"course_code": "SE501", "title": "Design Patterns Implementation",    "due_offset": 8,   "total_marks": 25},
    {"course_code": "SE502", "title": "Flutter App Prototype",            "due_offset": 6,   "total_marks": 40},
    {"course_code": "SE503", "title": "AWS Deployment Lab",               "due_offset": -2,  "total_marks": 25},
    {"course_code": "SE504", "title": "CI/CD Pipeline Setup",             "due_offset": 14,  "total_marks": 30},
]

# CS 2nd semester assignments
cs2_assignments = [
    {"course_code": "CS201", "title": "OOP Concepts Implementation",      "due_offset": -8,  "total_marks": 25},
    {"course_code": "CS201", "title": "Inheritance & Polymorphism Lab",   "due_offset": 9,   "total_marks": 20},
    {"course_code": "CS202", "title": "Linked List Implementation",       "due_offset": -4,  "total_marks": 30},
    {"course_code": "CS202", "title": "Binary Search Tree Lab",           "due_offset": 11,  "total_marks": 25},
    {"course_code": "CS203", "title": "Matrix Operations Assignment",     "due_offset": 4,   "total_marks": 20},
]

assignment_map = {}  # course_code+title → ObjectId

for a in (cs3_assignments + se5_assignments + cs2_assignments):
    due_date = datetime.now() + timedelta(days=a["due_offset"])
    doc = {
        "course_id"   : course_map[a["course_code"]],
        "course_code" : a["course_code"],
        "title"       : a["title"],
        "description" : f"Complete the {a['title']} as per the instructions shared in class.",
        "due_date"    : due_date,
        "total_marks" : a["total_marks"],
        "is_active"   : True,
        "created_at"  : random_date(25, 20),
    }
    aid = db["assignments"].insert_one(doc).inserted_id
    assignment_map[f"{a['course_code']}_{a['title']}"] = {
        "_id"        : aid,
        "due_offset" : a["due_offset"],
        "total_marks": a["total_marks"],
    }

print(f"   ✅  {len(assignment_map)} assignments inserted.\n")

# ─────────────────────────────────────────
# 5. ASSIGNMENT SUBMISSIONS
# ─────────────────────────────────────────
print("📤  Seeding assignment submissions...")

def make_submission(student_username, assignments_list, submit_all=False, skip_recent=False):
    """
    submit_all=True  → submit everything (Sara)
    skip_recent=True → skip upcoming ones, leave past ones unsubmitted (Ali - overdue)
    default          → mixed
    """
    submissions = []
    sid = student_ids[student_username]

    for a in assignments_list:
        key        = f"{a['course_code']}_{a['title']}"
        ainfo      = assignment_map[key]
        due_offset = ainfo["due_offset"]
        is_past    = due_offset < 0   # due date already passed
        is_future  = due_offset > 0

        if submit_all:
            # Submit everything, past ones on time, future ones early
            if is_past:
                status       = "submitted"
                submitted_at = datetime.now() - timedelta(days=abs(due_offset) + 1)
            else:
                status       = "submitted"
                submitted_at = datetime.now() - timedelta(days=1)
            marks = round(ainfo["total_marks"] * random.uniform(0.75, 0.97))

        elif skip_recent:
            # Ali: past assignments NOT submitted (overdue), future ones pending
            if is_past:
                status       = "overdue"
                submitted_at = None
                marks        = 0
            else:
                # Some future ones submitted, some pending
                if random.random() > 0.6:
                    status       = "submitted"
                    submitted_at = datetime.now() - timedelta(days=1)
                    marks        = round(ainfo["total_marks"] * random.uniform(0.65, 0.90))
                else:
                    status       = "pending"
                    submitted_at = None
                    marks        = 0
        else:
            # Mixed: mostly submitted
            if is_past:
                if random.random() > 0.3:
                    status       = "submitted"
                    submitted_at = datetime.now() - timedelta(days=abs(due_offset) - 1)
                    marks        = round(ainfo["total_marks"] * random.uniform(0.70, 0.95))
                else:
                    status       = "overdue"
                    submitted_at = None
                    marks        = 0
            else:
                status       = "pending"
                submitted_at = None
                marks        = 0

        submissions.append({
            "assignment_id" : ainfo["_id"],
            "student_id"    : sid,
            "status"        : status,
            "submitted_at"  : submitted_at,
            "marks_obtained": marks,
            "feedback"      : "Good work!" if marks > 0 else None,
        })
    return submissions

all_subs = []
all_subs += make_submission("ali_cs",  cs3_assignments, skip_recent=True)   # has overdue
all_subs += make_submission("sara_cs", cs3_assignments, submit_all=True)    # all submitted
all_subs += make_submission("zain_se", se5_assignments)                     # mixed
all_subs += make_submission("nida_cs", cs2_assignments, submit_all=True)    # all submitted

db["assignment_submissions"].insert_many(all_subs)
print(f"   ✅  {len(all_subs)} submissions inserted.\n")

# ─────────────────────────────────────────
# 6. GRADES (past semesters)
# ─────────────────────────────────────────
print("📊  Seeding grades...")

grades = []

def make_grades(student_username, semester, course_codes):
    sid = student_ids[student_username]
    for code in course_codes:
        mid   = random.randint(16, 25)
        final = random.randint(35, 50)
        total = mid + final
        pct   = total / 75
        if pct >= 0.90:   letter, gpa = "A+", 4.0
        elif pct >= 0.85: letter, gpa = "A",  4.0
        elif pct >= 0.80: letter, gpa = "A-", 3.7
        elif pct >= 0.75: letter, gpa = "B+", 3.3
        elif pct >= 0.70: letter, gpa = "B",  3.0
        elif pct >= 0.65: letter, gpa = "B-", 2.7
        elif pct >= 0.60: letter, gpa = "C+", 2.3
        else:             letter, gpa = "C",  2.0

        grades.append({
            "student_id"  : sid,
            "course_id"   : course_map[code],
            "course_code" : code,
            "semester"    : semester,
            "mid_marks"   : mid,
            "final_marks" : final,
            "total_marks" : total,
            "out_of"      : 75,
            "grade_letter": letter,
            "gpa_points"  : gpa,
            "session_year": "2023-24",
            "is_current"  : False,
        })

# Ali: grades for semester 1 and 2
make_grades("ali_cs",  1, ["CS101","CS102","CS103","ENG101"])
make_grades("ali_cs",  2, ["CS201","CS202","CS203","CS204"])

# Sara: grades for semester 1 and 2
make_grades("sara_cs", 1, ["CS101","CS102","CS103","ENG101"])
make_grades("sara_cs", 2, ["CS201","CS202","CS203","CS204"])

# Zain: grades for semester 1,2,3,4
make_grades("zain_se", 1, ["CS101","CS102","CS103","ENG101"])
make_grades("zain_se", 2, ["CS201","CS202","CS203","CS204"])
make_grades("zain_se", 3, ["CS301","CS302","CS303","CS304"])
make_grades("zain_se", 4, ["SE501","SE502","SE503","SE504"])

# Nida: grades for semester 1
make_grades("nida_cs", 1, ["CS101","CS102","CS103","ENG101"])

db["grades"].insert_many(grades)
print(f"   ✅  {len(grades)} grade records inserted.\n")

# ─────────────────────────────────────────
# 7. EXAMS
# ─────────────────────────────────────────
print("📅  Seeding exam schedules...")

exams = []

cs3_exams = [
    {"course_code": "CS301", "exam_type": "mid",   "days_from_now": 12, "time": "09:00 AM", "venue": "Hall A"},
    {"course_code": "CS302", "exam_type": "mid",   "days_from_now": 13, "time": "11:00 AM", "venue": "Hall B"},
    {"course_code": "CS303", "exam_type": "mid",   "days_from_now": 14, "time": "02:00 PM", "venue": "Hall A"},
    {"course_code": "CS304", "exam_type": "mid",   "days_from_now": 15, "time": "09:00 AM", "venue": "Lab 2"},
    {"course_code": "CS301", "exam_type": "final", "days_from_now": 45, "time": "09:00 AM", "venue": "Hall A"},
    {"course_code": "CS302", "exam_type": "final", "days_from_now": 47, "time": "11:00 AM", "venue": "Hall B"},
    {"course_code": "CS303", "exam_type": "final", "days_from_now": 48, "time": "02:00 PM", "venue": "Hall C"},
    {"course_code": "CS304", "exam_type": "final", "days_from_now": 50, "time": "09:00 AM", "venue": "Hall A"},
]

se5_exams = [
    {"course_code": "SE501", "exam_type": "mid",   "days_from_now": 10, "time": "10:00 AM", "venue": "Hall C"},
    {"course_code": "SE502", "exam_type": "mid",   "days_from_now": 11, "time": "01:00 PM", "venue": "Lab 1"},
    {"course_code": "SE503", "exam_type": "mid",   "days_from_now": 12, "time": "03:00 PM", "venue": "Hall B"},
    {"course_code": "SE504", "exam_type": "mid",   "days_from_now": 14, "time": "09:00 AM", "venue": "Hall A"},
    {"course_code": "SE501", "exam_type": "final", "days_from_now": 44, "time": "10:00 AM", "venue": "Hall C"},
    {"course_code": "SE502", "exam_type": "final", "days_from_now": 46, "time": "01:00 PM", "venue": "Lab 1"},
    {"course_code": "SE503", "exam_type": "final", "days_from_now": 48, "time": "03:00 PM", "venue": "Hall B"},
    {"course_code": "SE504", "exam_type": "final", "days_from_now": 50, "time": "09:00 AM", "venue": "Hall A"},
]

cs2_exams = [
    {"course_code": "CS201", "exam_type": "mid",   "days_from_now": 11, "time": "09:00 AM", "venue": "Hall B"},
    {"course_code": "CS202", "exam_type": "mid",   "days_from_now": 12, "time": "11:00 AM", "venue": "Hall A"},
    {"course_code": "CS203", "exam_type": "mid",   "days_from_now": 13, "time": "02:00 PM", "venue": "Lab 3"},
    {"course_code": "CS204", "exam_type": "mid",   "days_from_now": 15, "time": "09:00 AM", "venue": "Hall C"},
]

for e in (cs3_exams + se5_exams + cs2_exams):
    exams.append({
        "course_id"  : course_map[e["course_code"]],
        "course_code": e["course_code"],
        "exam_type"  : e["exam_type"],
        "exam_date"  : future_date(e["days_from_now"]),
        "start_time" : e["time"],
        "venue"      : e["venue"],
        "semester"   : 3 if e["course_code"].startswith("CS3") else
                       5 if e["course_code"].startswith("SE5") else 2,
        "duration_minutes": 180,
    })

db["exams"].insert_many(exams)
print(f"   ✅  {len(exams)} exam records inserted.\n")

# ─────────────────────────────────────────
# 8. FEES
# ─────────────────────────────────────────
print("💰  Seeding fee records...")

fee_records = []

fee_configs = [
    # username, semester, amount_due, amount_paid, status
    ("ali_cs",  1, 45000, 45000, "paid",    random_date(350, 340)),
    ("ali_cs",  2, 45000, 45000, "paid",    random_date(170, 160)),
    ("ali_cs",  3, 48000, 0,     "unpaid",  None),                    # UNPAID ← key for testing

    ("sara_cs", 1, 45000, 45000, "paid",    random_date(350, 340)),
    ("sara_cs", 2, 45000, 45000, "paid",    random_date(170, 160)),
    ("sara_cs", 3, 48000, 48000, "paid",    random_date(30, 20)),     # PAID ← can download

    ("zain_se", 1, 45000, 45000, "paid",    random_date(700, 690)),
    ("zain_se", 2, 45000, 45000, "paid",    random_date(520, 510)),
    ("zain_se", 3, 45000, 45000, "paid",    random_date(340, 330)),
    ("zain_se", 4, 46000, 46000, "paid",    random_date(160, 150)),
    ("zain_se", 5, 48000, 25000, "partial", random_date(20, 15)),     # PARTIAL ← some blocked

    ("nida_cs", 1, 45000, 45000, "paid",    random_date(350, 340)),
    ("nida_cs", 2, 48000, 48000, "paid",    random_date(30, 20)),
]

for username, sem, due, paid, status, paid_date in fee_configs:
    fee_records.append({
        "student_id"    : student_ids[username],
        "semester"      : sem,
        "session_year"  : "2024-25" if sem >= 3 else "2023-24",
        "amount_due"    : due,
        "amount_paid"   : paid,
        "balance"       : due - paid,
        "status"        : status,
        "due_date"      : future_date(30) if status == "unpaid" else random_date(5, 1),
        "payment_date"  : paid_date,
        "challan_number": f"CHN-{random.randint(10000,99999)}" if paid > 0 else None,
        "is_current_semester": sem in [3, 5, 2],
    })

db["fees"].insert_many(fee_records)
print(f"   ✅  {len(fee_records)} fee records inserted.\n")

# ─────────────────────────────────────────
# 9. INDEXES for fast queries
# ─────────────────────────────────────────
print("🔍  Creating indexes...")
db["users"].create_index("username",    unique=True)
db["users"].create_index("email",       unique=True)
db["students"].create_index("roll_number", unique=True)
db["students"].create_index("user_id")
db["enrollments"].create_index([("student_id", 1), ("semester", 1)])
db["grades"].create_index([("student_id", 1), ("semester", 1)])
db["fees"].create_index([("student_id", 1), ("semester", 1)])
db["assignment_submissions"].create_index([("student_id", 1), ("assignment_id", 1)])
db["exams"].create_index([("course_id", 1), ("exam_type", 1)])
print("   ✅  Indexes created.\n")

# ─────────────────────────────────────────
# 10. SUMMARY
# ─────────────────────────────────────────
print("=" * 50)
print("✅  SEED COMPLETE — IBA Sukkur University Portal")
print("=" * 50)
print(f"""
📦  Database   : {DB_NAME}
🌐  Mongo URI  : {MONGO_URI}

👤  LOGIN CREDENTIALS
┌─────────────┬──────────────┬───────────┬──────────┬────────────┐
│ Username    │ Password     │ Semester  │ Dept     │ Fees       │
├─────────────┼──────────────┼───────────┼──────────┼────────────┤
│ ali_cs      │ student123   │ 3rd       │ CS       │ ❌ UNPAID  │
│ sara_cs     │ student123   │ 3rd       │ CS       │ ✅ PAID    │
│ zain_se     │ student123   │ 5th       │ SE       │ ⚠️ PARTIAL │
│ nida_cs     │ student123   │ 2nd       │ CS       │ ✅ PAID    │
│ superadmin  │ admin123     │ —         │ —        │ superadmin │
└─────────────┴──────────────┴───────────┴──────────┴────────────┘

📊  Collections Created:
   users                 → {db['users'].count_documents({})} documents
   students              → {db['students'].count_documents({})} documents
   courses               → {db['courses'].count_documents({})} documents
   enrollments           → {db['enrollments'].count_documents({})} documents
   assignments           → {db['assignments'].count_documents({})} documents
   assignment_submissions→ {db['assignment_submissions'].count_documents({})} documents
   grades                → {db['grades'].count_documents({})} documents
   exams                 → {db['exams'].count_documents({})} documents
   fees                  → {db['fees'].count_documents({})} documents

🧪  TEST SCENARIOS READY:
   ali_cs  → Has overdue assignments + unpaid fees (transcript blocked)
   sara_cs → All clean, can download transcript
   zain_se → Partial fees, mixed assignments
   nida_cs → All clean, 2nd semester student
""")

client.close()
