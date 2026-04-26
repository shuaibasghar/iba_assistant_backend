"""
IBA Sukkur — Complete University Database Seed
================================================
University : IBA Sukkur (iba-suk.edu.pk)
DB Name    : iba_sukkur_data
Run        : python seed_iba_sukkur.py
Requires   : pip install pymongo bcrypt
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime, timedelta
from bson import ObjectId
import bcrypt, random, string

MONGO_URI  = "mongodb://localhost:27017"
DB_NAME    = "iba_sukkur_data"
DOMAIN     = "iba-suk.edu.pk"
UNI_NAME   = "IBA Sukkur"

client = MongoClient(MONGO_URI)
db     = client[DB_NAME]

# ─── helpers ────────────────────────────────────────────────────────────
def hp(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def ago(n): return datetime.now() - timedelta(days=n)
def fwd(n): return datetime.now() + timedelta(days=n)
def rdate(a,b): return datetime.now() - timedelta(days=random.randint(b,a))
def challan_no(): return "CHN-" + "".join(random.choices(string.digits,k=8))
def ticket_no():  return "TKT-2025-" + "".join(random.choices(string.digits,k=4))
def adm_no(dept,batch,n): return f"{dept}-{batch}-{n:03d}"

# ─── drop everything ────────────────────────────────────────────────────
print("🗑️  Dropping existing database iba_sukkur_data ...")
client.drop_database(DB_NAME)
db = client[DB_NAME]
print("✅  Fresh database created.\n")

# ════════════════════════════════════════════════════════════════════════
# 1. DEPARTMENTS
# ════════════════════════════════════════════════════════════════════════
print("🏫  Seeding departments...")
departments = [
    {"code":"CS",   "name":"Computer Science",            "faculty":"Technology",     "hod":"Dr. Ghulam Mujtaba Shaikh",  "established":2005, "total_semesters":8},
    {"code":"AI",   "name":"Artificial Intelligence",     "faculty":"Technology",     "hod":"Dr. Sadia Anwar",            "established":2020, "total_semesters":8},
    {"code":"BBA",  "name":"Business Administration",     "faculty":"Management",     "hod":"Dr. Khalid Mehmood",         "established":2001, "total_semesters":8},
    {"code":"MATH", "name":"Mathematics",                 "faculty":"Science",        "hod":"Dr. Noor Muhammad Shaikh",   "established":2003, "total_semesters":8},
    {"code":"SE",   "name":"Software Engineering",        "faculty":"Technology",     "hod":"Dr. Zulfiqar Ali",           "established":2015, "total_semesters":8},
]
dept_ids = {}
for d in departments:
    d["university"] = UNI_NAME
    dept_ids[d["code"]] = db["departments"].insert_one(d).inserted_id
print(f"   ✅  {len(departments)} departments.\n")

# ════════════════════════════════════════════════════════════════════════
# 2. COURSES
# ════════════════════════════════════════════════════════════════════════
print("📚  Seeding courses...")
courses_raw = [
    # CS
    ("CS101","Intro to Programming",          "CS",1,3),
    ("CS102","Discrete Mathematics",          "CS",1,3),
    ("CS103","Digital Logic Design",          "CS",1,3),
    ("ENG101","English Communication",        "CS",1,2),
    ("CS201","Object Oriented Programming",   "CS",2,3),
    ("CS202","Data Structures",               "CS",2,3),
    ("CS203","Linear Algebra",                "CS",2,3),
    ("CS204","Computer Organization",         "CS",2,3),
    ("CS301","Advanced NLP",                  "CS",3,3),
    ("CS302","Database Systems",              "CS",3,3),
    ("CS303","Operating Systems",             "CS",3,3),
    ("CS304","Software Engineering",          "CS",3,3),
    ("CS401","Computer Networks",             "CS",4,3),
    ("CS402","Artificial Intelligence",       "CS",4,3),
    ("CS403","Theory of Computation",         "CS",4,3),
    ("CS404","Web Engineering",               "CS",4,3),
    # AI
    ("AI101","Python for AI",                 "AI",1,3),
    ("AI102","Statistics for AI",             "AI",1,3),
    ("AI103","Linear Algebra",                "AI",1,3),
    ("ENG101B","Technical Communication",     "AI",1,2),
    ("AI201","Machine Learning",              "AI",2,3),
    ("AI202","Deep Learning",                 "AI",2,3),
    ("AI203","Computer Vision",               "AI",2,3),
    ("AI204","NLP Fundamentals",              "AI",2,3),
    ("AI301","Reinforcement Learning",        "AI",3,3),
    ("AI302","Generative AI",                 "AI",3,3),
    ("AI303","AI Ethics & Safety",            "AI",3,2),
    ("AI304","Research Methods",              "AI",3,3),
    # BBA
    ("BBA101","Principles of Management",     "BBA",1,3),
    ("BBA102","Business Mathematics",         "BBA",1,3),
    ("BBA103","Financial Accounting",         "BBA",1,3),
    ("ENG101C","Business Communication",      "BBA",1,2),
    ("BBA201","Marketing Management",         "BBA",2,3),
    ("BBA202","Microeconomics",               "BBA",2,3),
    ("BBA203","Cost Accounting",              "BBA",2,3),
    ("BBA204","Business Statistics",          "BBA",2,3),
    ("BBA301","Strategic Management",         "BBA",3,3),
    ("BBA302","Human Resource Management",    "BBA",3,3),
    ("BBA303","Business Finance",             "BBA",3,3),
    # MATH
    ("MTH101","Calculus I",                   "MATH",1,3),
    ("MTH102","Discrete Math",                "MATH",1,3),
    ("MTH103","Linear Algebra",               "MATH",1,3),
    ("ENG101D","Academic Writing",            "MATH",1,2),
    ("MTH201","Calculus II",                  "MATH",2,3),
    ("MTH202","Probability Theory",           "MATH",2,3),
    ("MTH203","Numerical Methods",            "MATH",2,3),
    ("MTH204","Abstract Algebra",             "MATH",2,3),
    ("MTH301","Real Analysis",                "MATH",3,3),
    ("MTH302","Differential Equations",       "MATH",3,3),
    ("MTH303","Complex Analysis",             "MATH",3,3),
    # SE
    ("SE101","Intro to SE",                   "SE",1,3),
    ("SE102","Programming Fundamentals",      "SE",1,3),
    ("SE103","Discrete Structures",           "SE",1,3),
    ("SE201","OOP with Java",                 "SE",2,3),
    ("SE202","Data Structures",               "SE",2,3),
    ("SE203","Software Requirements",         "SE",2,3),
    ("SE301","Software Architecture",         "SE",3,3),
    ("SE302","Agile Development",             "SE",3,3),
    ("SE303","Testing & QA",                  "SE",3,3),
]
course_ids = {}
for cc,cn,dept,sem,cr in courses_raw:
    oid = db["courses"].insert_one({
        "course_code":cc,"course_name":cn,"department":dept,
        "semester":sem,"credit_hours":cr,"university":UNI_NAME,
        "is_active":True
    }).inserted_id
    course_ids[cc] = oid
print(f"   ✅  {len(courses_raw)} courses.\n")

# ════════════════════════════════════════════════════════════════════════
# 3. TEACHER STAFF
# ════════════════════════════════════════════════════════════════════════
print("👨‍🏫  Seeding teachers...")
teachers_raw = [
    # CS teachers
    ("Dr. Ghulam Mujtaba Shaikh","gmshaikn","Prof123!","CS","Professor","HOD","CS301,CS302"),
    ("Dr. Sadia Anwar",          "sanwar",  "Prof123!","CS","Assoc. Prof","","CS303,CS304"),
    ("Dr. Imran Ali Shah",       "ishah",   "Prof123!","CS","Asst. Prof","","CS201,CS202"),
    ("Ms. Nadia Qureshi",        "nqureshi","Prof123!","CS","Lecturer","","CS101,CS102"),
    # AI teachers
    ("Dr. Tariq Mahmood",        "tmahmood","Prof123!","AI","Professor","HOD","AI201,AI202"),
    ("Dr. Zara Fatima",          "zfatima", "Prof123!","AI","Assoc. Prof","","AI203,AI204"),
    ("Mr. Asad Hussain",         "ahussain","Prof123!","AI","Lecturer","","AI101,AI102"),
    # BBA teachers
    ("Dr. Khalid Mehmood",       "kmehmood","Prof123!","BBA","Professor","HOD","BBA301,BBA302"),
    ("Ms. Sana Shaikh",          "sshaikh", "Prof123!","BBA","Asst. Prof","","BBA101,BBA201"),
    ("Mr. Faisal Raza",          "fraza",   "Prof123!","BBA","Lecturer","","BBA102,BBA202"),
    # MATH teachers
    ("Dr. Noor Muhammad Shaikh", "nmshaikh","Prof123!","MATH","Professor","HOD","MTH301,MTH302"),
    ("Dr. Rukhsar Bibi",         "rbibi",   "Prof123!","MATH","Asst. Prof","","MTH101,MTH201"),
    # SE teachers
    ("Dr. Zulfiqar Ali",         "zali",    "Prof123!","SE","Professor","HOD","SE301,SE302"),
    ("Mr. Bilal Ahmed",          "bahmed",  "Prof123!","SE","Lecturer","","SE101,SE201"),
]
teacher_ids   = {}
teacher_uids  = {}
for fn,un,pw,dept,desig,role,courses_str in teachers_raw:
    first = fn.split()[-1].lower()[:3]
    email = f"{un}@{DOMAIN}"
    uid = db["users"].insert_one({
        "username":un,"email":email,"password_hash":hp(pw),
        "role":"teacher","is_active":True,"created_at":ago(400),
        "last_login":ago(random.randint(1,5)),"university":UNI_NAME
    }).inserted_id
    course_list = [c.strip() for c in courses_str.split(",") if c.strip()]
    tid = db["teachers"].insert_one({
        "user_id":uid,"full_name":fn,"employee_id":f"TCH-{random.randint(1000,9999)}",
        "email":email,"department":dept,"designation":desig,"role_note":role,
        "assigned_courses":[course_ids[c] for c in course_list if c in course_ids],
        "assigned_course_codes":course_list,
        "phone":f"030{random.randint(10000000,99999999)}",
        "joining_date":ago(random.randint(365,1800)),
        "qualification":"PhD" if desig=="Professor" or desig=="Assoc. Prof" else "MS",
        "status":"active","university":UNI_NAME
    }).inserted_id
    db["users"].update_one({"_id":uid},{"$set":{"teacher_id":tid}})
    teacher_ids[un]  = tid
    teacher_uids[un] = uid

print(f"   ✅  {len(teachers_raw)} teachers.\n")

# ════════════════════════════════════════════════════════════════════════
# 4. STAFF (Admin, Exam, Hostel, Library, Finance, Admission)
# ════════════════════════════════════════════════════════════════════════
print("🏢  Seeding staff...")
staff_raw = [
    # name, username, department, role
    ("Muhammad Saleem",   "msaleem",   "Administration","admin_staff"),
    ("Rukhsana Khatoon",  "rkhatoon",  "Administration","admin_staff"),
    ("Jawad Ali Soomro",  "jasoomro",  "Examination",   "exam_staff"),
    ("Amna Bibi",         "amnabibi",  "Examination",   "exam_staff"),
    ("Riaz Hussain",      "rhussain",  "Hostel",        "hostel_staff"),
    ("Nadia Parveen",     "nparveen",  "Hostel",        "hostel_staff"),
    ("Muhammad Yousuf",   "myousuf",   "Library",       "library_staff"),
    ("Saima Shaikh",      "sshaikh2",  "Library",       "library_staff"),
    ("Ghulam Rasool",     "grasool",   "Finance",       "finance_staff"),
    ("Nasreen Fatima",    "nfatima",   "Finance",       "finance_staff"),
    ("Tariq Jamali",      "tjamali",   "Admission",     "admission_staff"),
    ("Zubeda Khatoon",    "zkhatoon",  "Admission",     "admission_staff"),
    ("Ali Nawaz Memon",   "anmemon",   "IT",            "it_staff"),
]
staff_ids = {}
for fn,un,dept,role in staff_raw:
    email = f"{un}@{DOMAIN}"
    uid = db["users"].insert_one({
        "username":un,"email":email,"password_hash":hp("Staff@123"),
        "role":role,"is_active":True,"created_at":ago(500),
        "last_login":ago(random.randint(1,10)),"university":UNI_NAME
    }).inserted_id
    sid = db["staff"].insert_one({
        "user_id":uid,"full_name":fn,"employee_id":f"STF-{random.randint(1000,9999)}",
        "email":email,"department":dept,"role":role,
        "phone":f"030{random.randint(10000000,99999999)}",
        "joining_date":ago(random.randint(200,1200)),
        "status":"active","university":UNI_NAME
    }).inserted_id
    db["users"].update_one({"_id":uid},{"$set":{"staff_id":sid}})
    staff_ids[un] = sid

# Superadmin — JWT + portal use role string `superadmin` (not legacy `superuser`).
sa_email = f"admin@{DOMAIN}"
sa_pw_hash = hp("SuperAdmin@123")
sa_uid = db["users"].insert_one({
    "username": "superadmin",
    "email": sa_email,
    "password_hash": sa_pw_hash,
    "role": "superadmin",
    "is_active": True,
    "created_at": ago(600),
    "last_login": ago(1),
    "university": UNI_NAME,
}).inserted_id
db["superadmins"].insert_one({
    "user_id": sa_uid,
    "full_name": "System Superadmin",
    "email": sa_email,
    "employee_id": "SUP-001",
    "department": "System",
    "password_hash": sa_pw_hash,
    "designation": "Superadmin",
    "role": "superadmin",
    "status": "active",
    "university": UNI_NAME,
    "created_at": ago(600),
})
print(f"   ✅  {len(staff_raw)} staff + 1 superadmin (users + superadmins).\n")

# ════════════════════════════════════════════════════════════════════════
# 5. STUDENTS (60 students across departments)
# ════════════════════════════════════════════════════════════════════════
print("🎓  Seeding 60 students...")

pk_first = ["Ali","Umar","Hassan","Hamza","Bilal","Zain","Asad","Fahad","Omar","Junaid",
            "Shoaib","Naeem","Arif","Waseem","Imran","Khalid","Tariq","Faisal","Qasim","Adeel",
            "Ayesha","Fatima","Zara","Nida","Sana","Maryam","Iqra","Hina","Amna","Sobia",
            "Noor","Rabia","Sara","Mehwish","Aisha","Bushra","Huma","Lubna","Saima","Parveen"]
pk_last  = ["Khan","Ali","Ahmed","Shah","Soomro","Memon","Bhutto","Laghari","Qureshi","Raza",
            "Shaikh","Jamali","Chandio","Tunio","Panhwar","Mastoi","Jatoi","Talpur","Bhatti","Rajput"]

dept_student_count = {"CS":15,"AI":12,"BBA":15,"MATH":10,"SE":8}

dept_semesters  = {"CS":[1,2,3,4],"AI":[1,2,3],"BBA":[1,2,3,4],"MATH":[1,2,3],"SE":[1,2,3]}
dept_fee_amt    = {"CS":48000,"AI":50000,"BBA":42000,"MATH":38000,"SE":48000}

# courses per dept per semester
dept_courses = {
    "CS":  {1:["CS101","CS102","CS103","ENG101"],
            2:["CS201","CS202","CS203","CS204"],
            3:["CS301","CS302","CS303","CS304"],
            4:["CS401","CS402","CS403","CS404"]},
    "AI":  {1:["AI101","AI102","AI103","ENG101B"],
            2:["AI201","AI202","AI203","AI204"],
            3:["AI301","AI302","AI303","AI304"]},
    "BBA": {1:["BBA101","BBA102","BBA103","ENG101C"],
            2:["BBA201","BBA202","BBA203","BBA204"],
            3:["BBA301","BBA302","BBA303"],
            4:["BBA301","BBA302","BBA303"]},
    "MATH":{1:["MTH101","MTH102","MTH103","ENG101D"],
            2:["MTH201","MTH202","MTH203","MTH204"],
            3:["MTH301","MTH302","MTH303"]},
    "SE":  {1:["SE101","SE102","SE103"],
            2:["SE201","SE202","SE203"],
            3:["SE301","SE302","SE303"]},
}

student_ids = {}
student_profiles = {}
used_names = set()

counter = {"CS":1,"AI":1,"BBA":1,"MATH":1,"SE":1}
batch_map = {1:"2025",2:"2024",3:"2024",4:"2023"}
all_students = []

for dept, count in dept_student_count.items():
    sems = dept_semesters[dept]
    per_sem = max(1, count // len(sems))
    student_list_for_dept = []
    for sem in sems:
        for _ in range(per_sem if sem != sems[-1] else count - len(student_list_for_dept)):
            if len(student_list_for_dept) >= count:
                break
            fn = random.choice(pk_first)
            ln = random.choice(pk_last)
            full = f"{fn} {ln}"
            while full in used_names:
                fn = random.choice(pk_first)
                ln = random.choice(pk_last)
                full = f"{fn} {ln}"
            used_names.add(full)

            n = counter[dept]
            counter[dept] += 1
            roll = adm_no(dept, batch_map.get(sem,"2024"), n)
            un   = f"{fn.lower()}{n}_{dept.lower()}"
            email= f"{fn.lower()}.{ln.lower()}{n}@{DOMAIN}"

            uid = db["users"].insert_one({
                "username":un,"email":email,"password_hash":hp("Student@123"),
                "role":"student","is_active":True,"created_at":ago(random.randint(200,600)),
                "last_login":ago(random.randint(0,7)),"university":UNI_NAME
            }).inserted_id

            fee_status = random.choices(["paid","unpaid","partial"],[0.6,0.25,0.15])[0]
            sid = db["students"].insert_one({
                "user_id":uid,"full_name":full,"roll_number":roll,
                "email":email,"department":dept,"semester":sem,
                "batch":batch_map.get(sem,"2024"),
                "dob":datetime(random.randint(2000,2004),random.randint(1,12),random.randint(1,28)),
                "phone":f"030{random.randint(10000000,99999999)}",
                "address":random.choice(["House 12 Sukkur","Block A Hyderabad","Street 4 Karachi",
                                         "Flat 7 Larkana","Sector G Islamabad","Near Masjid Nawabshah"]),
                "gender":random.choice(["Male","Female"]),
                "religion":"Islam",
                "current_fee_status":fee_status,
                "cgpa":round(random.uniform(2.5,3.9),2),
                "status":"active","hostel":random.choice([True,False]),
                "university":UNI_NAME,"created_at":ago(random.randint(200,600))
            }).inserted_id

            db["users"].update_one({"_id":uid},{"$set":{"student_id":sid}})
            student_ids[un] = sid
            student_profiles[str(sid)] = {
                "username":un,"full_name":full,"department":dept,
                "semester":sem,"fee_status":fee_status,"uid":uid
            }
            student_list_for_dept.append((sid,uid,un,full,dept,sem,fee_status,roll))
            all_students.append((sid,uid,un,full,dept,sem,fee_status,roll))

print(f"   ✅  {len(all_students)} students.\n")

# ════════════════════════════════════════════════════════════════════════
# 6. ENROLLMENTS
# ════════════════════════════════════════════════════════════════════════
print("📋  Seeding enrollments...")
enrollments = []
for sid,uid,un,fn,dept,sem,fs,roll in all_students:
    for cc in dept_courses.get(dept,{}).get(sem,[]):
        if cc in course_ids:
            enrollments.append({
                "student_id":sid,"course_id":course_ids[cc],"course_code":cc,
                "department":dept,"semester":sem,"session_year":"2024-25",
                "enrolled_at":ago(random.randint(80,90)),"status":"active","university":UNI_NAME
            })
db["enrollments"].insert_many(enrollments)
print(f"   ✅  {len(enrollments)} enrollments.\n")

# ════════════════════════════════════════════════════════════════════════
# 7. ASSIGNMENTS (created by teacher, assigned to course)
# ════════════════════════════════════════════════════════════════════════
print("📝  Seeding assignments...")

# teacher → course mapping for assignment creation
teacher_course_map = {}
for fn,un,pw,dept,desig,role,courses_str in teachers_raw:
    for c in [x.strip() for x in courses_str.split(",") if x.strip()]:
        teacher_course_map[c] = teacher_ids[un]

assignment_templates = {
    "CS301":[("Text Preprocessing Pipeline",20,-12),("TF-IDF vs Word2Vec",25,6),("BERT Fine-tuning",30,18)],
    "CS302":[("ER Diagram Design",20,-5),("SQL Optimization Lab",20,8)],
    "CS303":[("Process Scheduling Sim",25,-15),("Memory Management Report",20,11)],
    "CS304":[("SRS Document",30,-3),("UML Diagrams",25,14)],
    "CS201":[("OOP Concepts",25,-8),("Inheritance Lab",20,10)],
    "CS202":[("Linked List",30,-4),("BST Lab",25,12)],
    "AI201":[("Linear Regression",25,-6),("Decision Trees",30,9)],
    "AI202":[("CNN Image Classifier",35,-10),("RNN Text Generation",30,7)],
    "BBA101":[("Management Essay",20,-7),("Case Study Analysis",25,10)],
    "BBA201":[("Marketing Plan",30,-5),("Brand Analysis",25,12)],
    "MTH101":[("Calculus Problem Set",20,-9),("Integration Lab",20,8)],
    "MTH201":[("Series Convergence",25,-6),("Multivariable Calculus",20,11)],
    "SE301":[("Architecture Design",30,-4),("Pattern Implementation",25,9)],
    "SE201":[("Java OOP Project",35,-8),("Design Patterns",25,13)],
}
assignment_ids = {}
assignments_by_course = {}
for cc, alist in assignment_templates.items():
    if cc not in course_ids: continue
    tid = teacher_course_map.get(cc)
    assignments_by_course[cc] = []
    for title, marks, offset in alist:
        aid = db["assignments"].insert_one({
            "course_id":course_ids[cc],"course_code":cc,
            "title":title,
            "description":f"Complete the {title} as per instructions shared in class.",
            "created_by_teacher":tid,
            "total_marks":marks,
            "due_date":fwd(offset) if offset > 0 else ago(abs(offset)),
            "is_past": offset < 0,
            "is_active":True,"semester":None,
            "created_at":ago(random.randint(15,25)),"university":UNI_NAME
        }).inserted_id
        assignment_ids[f"{cc}_{title}"] = aid
        assignments_by_course[cc].append({"_id":aid,"title":title,"marks":marks,"offset":offset})

print(f"   ✅  {len(assignment_ids)} assignments.\n")

# ════════════════════════════════════════════════════════════════════════
# 8. ASSIGNMENT SUBMISSIONS (with teacher & student flags)
# ════════════════════════════════════════════════════════════════════════
print("📤  Seeding assignment submissions...")
submissions = []
for sid,uid,un,fn,dept,sem,fs,roll in all_students:
    for cc in dept_courses.get(dept,{}).get(sem,[]):
        if cc not in assignments_by_course: continue
        tid = teacher_course_map.get(cc)
        for a in assignments_by_course[cc]:
            is_past = a["offset"] < 0
            r = random.random()
            if is_past:
                if r < 0.65: status,submitted_at,marks = "submitted", ago(abs(a["offset"])-1), round(a["marks"]*random.uniform(0.6,0.97))
                else:         status,submitted_at,marks = "overdue",   None, 0
            else:
                if r < 0.4:  status,submitted_at,marks = "submitted", ago(1), round(a["marks"]*random.uniform(0.7,0.97))
                else:         status,submitted_at,marks = "pending",   None, 0
            submissions.append({
                "assignment_id":a["_id"],"course_id":course_ids[cc],"course_code":cc,
                "student_id":sid,"student_name":fn,"student_roll":roll,
                "teacher_id":tid,
                "status":status,"submitted_at":submitted_at,
                "marks_obtained":marks,"out_of":a["marks"],
                "feedback":"Good work!" if marks > 0 else None,
                "graded":marks > 0,"graded_at":ago(1) if marks>0 else None,
                "is_flagged": random.random() < 0.05,
                "flag_reason":"plagiarism_check" if random.random()<0.05 else None,
                "university":UNI_NAME
            })
if submissions: db["assignment_submissions"].insert_many(submissions)
print(f"   ✅  {len(submissions)} submissions.\n")

# ════════════════════════════════════════════════════════════════════════
# 9. GRADES (past semesters)
# ════════════════════════════════════════════════════════════════════════
print("📊  Seeding grades...")
grades = []
def grade_letter(pct):
    if pct>=0.90: return "A+",4.0
    if pct>=0.85: return "A",4.0
    if pct>=0.80: return "A-",3.7
    if pct>=0.75: return "B+",3.3
    if pct>=0.70: return "B",3.0
    if pct>=0.65: return "B-",2.7
    if pct>=0.60: return "C+",2.3
    if pct>=0.55: return "C",2.0
    return "F",0.0

for sid,uid,un,fn,dept,sem,fs,roll in all_students:
    for past_sem in range(1, sem):
        for cc in dept_courses.get(dept,{}).get(past_sem,[]):
            if cc not in course_ids: continue
            mid=random.randint(14,25); final=random.randint(30,50); total=mid+final
            gl,gp = grade_letter(total/75)
            grades.append({
                "student_id":sid,"course_id":course_ids[cc],"course_code":cc,
                "student_name":fn,"semester":past_sem,"department":dept,
                "mid_marks":mid,"final_marks":final,"total_marks":total,"out_of":75,
                "grade_letter":gl,"gpa_points":gp,
                "session_year":"2023-24","is_current":False,"university":UNI_NAME
            })
if grades: db["grades"].insert_many(grades)
print(f"   ✅  {len(grades)} grade records.\n")

# ════════════════════════════════════════════════════════════════════════
# 10. SEMESTER RESULTS
# ════════════════════════════════════════════════════════════════════════
print("🏆  Seeding semester results...")
results = []
for sid,uid,un,fn,dept,sem,fs,roll in all_students:
    running_cgpa = 0
    for past_sem in range(1, sem):
        sgpa = round(random.uniform(2.6,3.9),2)
        running_cgpa = round((running_cgpa*(past_sem-1) + sgpa)/past_sem,2)
        results.append({
            "student_id":sid,"student_name":fn,"department":dept,
            "semester":past_sem,"sgpa":sgpa,"cgpa":running_cgpa,
            "total_credit_hours":past_sem*12,
            "passed":random.randint(3,4),"failed":random.randint(0,1),
            "result_status":random.choices(["pass","probation"],[0.9,0.1])[0],
            "session_year":"2023-24","university":UNI_NAME
        })
if results: db["semester_results"].insert_many(results)
print(f"   ✅  {len(results)} semester results.\n")

# ════════════════════════════════════════════════════════════════════════
# 11. FEES & CHALLANS
# ════════════════════════════════════════════════════════════════════════
print("💰  Seeding fees & challans...")
fees = []; challans = []
for sid,uid,un,fn,dept,sem,fs,roll in all_students:
    amount = dept_fee_amt.get(dept,45000)
    for past_sem in range(1, sem):
        paid_date = rdate(past_sem*90+90, past_sem*90+80)
        cn = challan_no()
        fees.append({
            "student_id":sid,"student_name":fn,"roll_number":roll,"department":dept,
            "semester":past_sem,"session_year":"2023-24",
            "amount_due":amount,"amount_paid":amount,"balance":0,
            "status":"paid","due_date":rdate(past_sem*90+30,past_sem*90+20),
            "payment_date":paid_date,"challan_number":cn,
            "is_current_semester":False,"university":UNI_NAME
        })
        challans.append({
            "challan_number":cn,"student_id":sid,"student_name":fn,
            "roll_number":roll,"department":dept,"semester":past_sem,
            "amount":amount,"issued_date":rdate(past_sem*90+40,past_sem*90+35),
            "paid_date":paid_date,"status":"paid",
            "bank":"HBL","university":UNI_NAME
        })
    # current semester
    cn = challan_no()
    if fs == "paid":
        paid = amount; balance = 0; pd = ago(random.randint(20,40))
        challans.append({
            "challan_number":cn,"student_id":sid,"student_name":fn,
            "roll_number":roll,"department":dept,"semester":sem,
            "amount":amount,"issued_date":ago(50),"paid_date":pd,
            "status":"paid","bank":random.choice(["HBL","Bank Alfalah","MCB"]),
            "university":UNI_NAME
        })
    elif fs == "partial":
        paid = amount//2; balance = amount-paid; pd = ago(20)
        challans.append({
            "challan_number":cn,"student_id":sid,"student_name":fn,
            "roll_number":roll,"department":dept,"semester":sem,
            "amount":paid,"issued_date":ago(30),"paid_date":pd,
            "status":"partial","bank":"HBL","university":UNI_NAME
        })
    else:
        paid = 0; balance = amount; pd = None
        challans.append({
            "challan_number":cn,"student_id":sid,"student_name":fn,
            "roll_number":roll,"department":dept,"semester":sem,
            "amount":0,"issued_date":ago(20),"paid_date":None,
            "status":"unpaid","bank":None,"university":UNI_NAME
        })
    fees.append({
        "student_id":sid,"student_name":fn,"roll_number":roll,"department":dept,
        "semester":sem,"session_year":"2024-25",
        "amount_due":amount,"amount_paid":paid,"balance":balance,
        "status":fs,"due_date":fwd(15) if fs!="paid" else ago(20),
        "payment_date":pd,"challan_number":cn,
        "is_current_semester":True,"university":UNI_NAME
    })
db["fees"].insert_many(fees)
db["challans"].insert_many(challans)
print(f"   ✅  {len(fees)} fee records, {len(challans)} challans.\n")

# ════════════════════════════════════════════════════════════════════════
# 12. ATTENDANCE
# ════════════════════════════════════════════════════════════════════════
print("📋  Seeding attendance...")
attendance = []
for sid,uid,un,fn,dept,sem,fs,roll in all_students:
    for cc in dept_courses.get(dept,{}).get(sem,[]):
        if cc not in course_ids: continue
        total = random.randint(28,36)
        attended = random.randint(int(total*0.5), total)
        pct = round(attended/total*100,1)
        attendance.append({
            "student_id":sid,"student_name":fn,"course_id":course_ids[cc],
            "course_code":cc,"department":dept,"semester":sem,
            "total_classes":total,"attended":attended,"absent":total-attended,
            "percentage":pct,
            "status":"good" if pct>=75 else "warning" if pct>=60 else "critical",
            "session_year":"2024-25","last_updated":ago(1),"university":UNI_NAME
        })
db["attendance"].insert_many(attendance)
print(f"   ✅  {len(attendance)} attendance records.\n")

# ════════════════════════════════════════════════════════════════════════
# 13. TIMETABLE
# ════════════════════════════════════════════════════════════════════════
print("🕐  Seeding timetable...")
days = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
slots = [("08:00","09:30"),("09:45","11:15"),("11:30","13:00"),("14:00","15:30"),("15:45","17:15")]
rooms = ["Room 101","Room 102","Room 201","Room 202","CS-Lab 1","CS-Lab 2","AI-Lab","SE-Lab","Room 301","Hall A"]

timetable = []
for dept, sem_map in dept_courses.items():
    for sem, course_list in sem_map.items():
        for i, cc in enumerate(course_list):
            if cc not in course_ids: continue
            timetable.append({
                "course_id":course_ids[cc],"course_code":cc,
                "department":dept,"semester":sem,
                "day":days[i % 5],"day_num":(i%5)+1,
                "start":slots[i%len(slots)][0],"end":slots[i%len(slots)][1],
                "room":random.choice(rooms),
                "session_year":"2024-25","university":UNI_NAME
            })
            if len(course_list) > 2:
                timetable.append({
                    "course_id":course_ids[cc],"course_code":cc,
                    "department":dept,"semester":sem,
                    "day":days[(i+2)%5],"day_num":((i+2)%5)+1,
                    "start":slots[(i+1)%len(slots)][0],"end":slots[(i+1)%len(slots)][1],
                    "room":random.choice(rooms),
                    "session_year":"2024-25","university":UNI_NAME
                })
db["timetable"].insert_many(timetable)
print(f"   ✅  {len(timetable)} timetable slots.\n")

# ════════════════════════════════════════════════════════════════════════
# 14. EXAMS & ADMIT CARDS
# ════════════════════════════════════════════════════════════════════════
print("📅  Seeding exams & admit cards...")
exams = []; admit_cards = []
exam_offset = 12
for dept, sem_map in dept_courses.items():
    for sem, course_list in sem_map.items():
        for i, cc in enumerate(course_list):
            if cc not in course_ids: continue
            mid_date = fwd(exam_offset + i)
            final_date = fwd(45 + i*2)
            for etype, edate in [("mid",mid_date),("final",final_date)]:
                eid = db["exams"].insert_one({
                    "course_id":course_ids[cc],"course_code":cc,
                    "department":dept,"semester":sem,
                    "exam_type":etype,"exam_date":edate,
                    "start_time":slots[i%len(slots)][0],
                    "venue":random.choice(["Hall A","Hall B","Hall C","Lab 1","Lab 2"]),
                    "duration_minutes":180,"session_year":"2024-25",
                    "total_marks":25 if etype=="mid" else 50,"university":UNI_NAME
                }).inserted_id
                # admit cards per student
                for sid,uid,un,fn,sdept,ssem,fs,roll in all_students:
                    if sdept==dept and ssem==sem:
                        fee_ok = (fs=="paid")
                        is_ready = fee_ok and random.random() > 0.1
                        admit_cards.append({
                            "exam_id":eid,"course_id":course_ids[cc],"course_code":cc,
                            "student_id":sid,"student_name":fn,"roll_number":roll,
                            "department":dept,"semester":sem,"exam_type":etype,
                            "exam_date":edate,"venue":random.choice(["Hall A","Hall B","Hall C"]),
                            "seat_number":f"{dept[0]}{sem}{random.randint(10,99)}",
                            "is_ready":is_ready,
                            "blocked_reason":None if is_ready else ("fee_unpaid" if not fee_ok else "admin_hold"),
                            "issued_at":ago(3) if is_ready else None,
                            "session_year":"2024-25","university":UNI_NAME
                        })
db["exams"].insert_many([]) if not list(db["exams"].find()) else None
if admit_cards: db["admit_cards"].insert_many(admit_cards)
print(f"   ✅  {db['exams'].count_documents({})} exams, {len(admit_cards)} admit cards.\n")

# ════════════════════════════════════════════════════════════════════════
# 15. TRANSCRIPTS & CERTIFICATES
# ════════════════════════════════════════════════════════════════════════
print("📄  Seeding transcripts & certificates...")
transcripts = []; certificates = []
for sid,uid,un,fn,dept,sem,fs,roll in all_students:
    fee_cleared = (fs == "paid")
    # Transcript
    transcripts.append({
        "student_id":sid,"student_name":fn,"roll_number":roll,
        "department":dept,"semester":sem,
        "requested":random.random()>0.5,
        "status": "issued" if fee_cleared and random.random()>0.4 else
                  "on_hold" if not fee_cleared else "pending",
        "blocked_reason": "fee_unpaid" if not fee_cleared else None,
        "issued_at": ago(random.randint(5,20)) if fee_cleared and random.random()>0.5 else None,
        "requested_at": ago(random.randint(1,30)),
        "ticket_number": ticket_no(),"university":UNI_NAME
    })
    # Enrollment certificate
    certificates.append({
        "student_id":sid,"student_name":fn,"roll_number":roll,
        "department":dept,"semester":sem,
        "certificate_type":"enrollment",
        "status": "issued" if fee_cleared and random.random()>0.5 else
                  "on_hold" if not fee_cleared else "pending",
        "blocked_reason": "fee_unpaid" if not fee_cleared else None,
        "issued_at": ago(random.randint(5,20)) if fee_cleared else None,
        "requested_at": ago(random.randint(1,30)),
        "ticket_number": ticket_no(),"university":UNI_NAME
    })
db["transcripts"].insert_many(transcripts)
db["certificates"].insert_many(certificates)
print(f"   ✅  {len(transcripts)} transcripts, {len(certificates)} certificates.\n")

# ════════════════════════════════════════════════════════════════════════
# 16. COMPLAINTS & REQUESTS
# ════════════════════════════════════════════════════════════════════════
print("📨  Seeding complaints...")
req_types = ["transcript_request","fee_complaint","attendance_complaint",
             "grade_review","hostel_complaint","library_query","general_query"]
statuses  = ["pending","in_progress","resolved","on_hold"]
complaints = []
for sid,uid,un,fn,dept,sem,fs,roll in random.sample(all_students, min(30, len(all_students))):
    rtype = random.choice(req_types)
    stat  = "on_hold" if (rtype=="transcript_request" and fs!="paid") else random.choice(statuses)
    complaints.append({
        "student_id":sid,"student_name":fn,"roll_number":roll,"department":dept,
        "type":rtype,
        "subject":f"{rtype.replace('_',' ').title()} - {fn}",
        "description":f"Request regarding {rtype.replace('_',' ')} for semester {sem}.",
        "status":stat,
        "hold_reason":"Fee unpaid" if stat=="on_hold" else None,
        "submitted_at":ago(random.randint(1,20)),
        "resolved_at":ago(random.randint(0,5)) if stat=="resolved" else None,
        "response":"Being processed." if stat!="resolved" else "Issue resolved.",
        "ticket_number":ticket_no(),
        "assigned_to_staff": random.choice(list(staff_ids.values())),
        "university":UNI_NAME
    })
db["complaints"].insert_many(complaints)
print(f"   ✅  {len(complaints)} complaints.\n")

# ════════════════════════════════════════════════════════════════════════
# 17. LIBRARY
# ════════════════════════════════════════════════════════════════════════
print("📚  Seeding library...")
books_pool = [
    ("Introduction to Algorithms","Cormen"),("Clean Code","Robert C. Martin"),
    ("Deep Learning","Goodfellow"),("Database System Concepts","Silberschatz"),
    ("Operating System Concepts","Silberschatz"),("Principles of Marketing","Kotler"),
    ("Calculus","James Stewart"),("Speech & Language Processing","Jurafsky"),
    ("Head First Java","Kathy Sierra"),("Python Crash Course","Eric Matthes"),
]
library = []
for sid,uid,un,fn,dept,sem,fs,roll in random.sample(all_students, min(40,len(all_students))):
    for _ in range(random.randint(0,2)):
        book = random.choice(books_pool)
        issued = ago(random.randint(5,25))
        due    = issued + timedelta(days=14)
        overdue = datetime.now() > due
        returned= random.random()>0.5
        library.append({
            "student_id":sid,"student_name":fn,"roll_number":roll,
            "book_title":book[0],"author":book[1],
            "issued_date":issued,"due_date":due,
            "return_date": due + timedelta(days=random.randint(0,3)) if returned else None,
            "status": "returned" if returned else ("overdue" if overdue else "issued"),
            "fine_per_day":10,
            "fine_amount": max(0,(datetime.now()-due).days*10) if overdue and not returned else 0,
            "fine_paid":False,"university":UNI_NAME
        })
if library: db["library"].insert_many(library)
print(f"   ✅  {len(library)} library records.\n")

# ════════════════════════════════════════════════════════════════════════
# 18. SCHOLARSHIPS
# ════════════════════════════════════════════════════════════════════════
print("🎓  Seeding scholarships...")
scholarship_types = [
    ("HEC Need-Based","HEC Pakistan",24000),
    ("IBA Merit Scholarship","IBA Sukkur",35000),
    ("Sindh Government Scholarship","Govt of Sindh",20000),
    ("PM Youth Laptop Scheme","Federal Govt",15000),
]
scholarships = []
for sid,uid,un,fn,dept,sem,fs,roll in random.sample(all_students, min(20,len(all_students))):
    stype = random.choice(scholarship_types)
    stat  = random.choice(["active","applied","expired"])
    scholarships.append({
        "student_id":sid,"student_name":fn,"roll_number":roll,"department":dept,
        "scholarship_name":stype[0],"provider":stype[1],
        "amount_per_semester":stype[2],
        "status":stat,
        "start_semester":1,"current_semester":sem,
        "next_disbursement": fwd(30) if stat=="active" else None,
        "last_disbursement": ago(90) if stat=="active" else None,
        "cgpa_requirement":2.5,"applied_at":ago(random.randint(30,200)),
        "approved_at": ago(random.randint(10,29)) if stat in ["active","expired"] else None,
        "university":UNI_NAME
    })
db["scholarships"].insert_many(scholarships)
print(f"   ✅  {len(scholarships)} scholarships.\n")

# ════════════════════════════════════════════════════════════════════════
# 19. HOSTEL
# ════════════════════════════════════════════════════════════════════════
print("🏠  Seeding hostel records...")
hostel_students = [(sid,fn,roll,dept) for sid,uid,un,fn,dept,sem,fs,roll in all_students if random.random()<0.4]
hostel_records  = []
rooms_h = [f"Block-{b}{n}" for b in ["A","B","C"] for n in range(101,115)]
for sid,fn,roll,dept in hostel_students:
    hostel_records.append({
        "student_id":sid,"student_name":fn,"roll_number":roll,"department":dept,
        "room_number":random.choice(rooms_h),
        "check_in_date":ago(random.randint(60,90)),
        "monthly_fee":5000,"status":"active",
        "warden":random.choice(["Mr. Riaz Hussain","Ms. Nadia Parveen"]),
        "university":UNI_NAME
    })
if hostel_records: db["hostel"].insert_many(hostel_records)
print(f"   ✅  {len(hostel_records)} hostel records.\n")

# ════════════════════════════════════════════════════════════════════════
# 20. EMPLOYEE SALARIES
# ════════════════════════════════════════════════════════════════════════
print("💼  Seeding salaries...")
salaries = []
# Teacher salaries
teacher_grade = {"Professor":150000,"Assoc. Prof":120000,"Asst. Prof":90000,"Lecturer":65000}
for fn,un,pw,dept,desig,role,_ in teachers_raw:
    base = teacher_grade.get(desig,65000)
    for month_offset in range(4):
        m = datetime.now().replace(day=1) - timedelta(days=30*month_offset)
        salaries.append({
            "employee_id":teacher_ids[un],"employee_name":fn,
            "employee_type":"teacher","department":dept,
            "month":m.strftime("%B %Y"),"basic_salary":base,
            "allowances":round(base*0.25),"deductions":round(base*0.05),
            "net_salary":round(base*1.20),
            "status":random.choice(["paid","paid","paid","pending"]),
            "paid_date": ago(month_offset*30+5) if random.random()>0.1 else None,
            "university":UNI_NAME
        })
# Staff salaries
for fn,un,dept,role in staff_raw:
    base = random.randint(35000,55000)
    for month_offset in range(4):
        m = datetime.now().replace(day=1) - timedelta(days=30*month_offset)
        salaries.append({
            "employee_id":staff_ids[un],"employee_name":fn,
            "employee_type":"staff","department":dept,
            "month":m.strftime("%B %Y"),"basic_salary":base,
            "allowances":round(base*0.15),"deductions":round(base*0.03),
            "net_salary":round(base*1.12),
            "status":random.choice(["paid","paid","pending"]),
            "paid_date": ago(month_offset*30+5) if random.random()>0.15 else None,
            "university":UNI_NAME
        })
db["salaries"].insert_many(salaries)
print(f"   ✅  {len(salaries)} salary records.\n")

# ════════════════════════════════════════════════════════════════════════
# 21. ANNOUNCEMENTS
# ════════════════════════════════════════════════════════════════════════
print("📢  Seeding announcements...")
announcements = [
    {"title":"Mid-Term Exam Schedule Released","body":"Mid-term exams begin in 12 days. Collect hall tickets from exam office.","category":"exam","target":"all","is_urgent":True,"posted_at":ago(2)},
    {"title":"Fee Submission Last Date — 30th April 2025","body":"Last date for fee submission is 30th April. Defaulters cannot appear in exams.","category":"fee","target":"all","is_urgent":True,"posted_at":ago(5)},
    {"title":"HEC Scholarship Applications Open","body":"HEC Need-Based Scholarship applications open. CGPA 2.5+ required. Apply by 10 May.","category":"scholarship","target":"all","is_urgent":False,"posted_at":ago(4)},
    {"title":"CS Department Seminar — AI in Healthcare","body":"Seminar on AI in Healthcare — 28 April, 10 AM, Main Auditorium. Certificates awarded.","category":"event","target":"department","departments":["CS","AI"],"is_urgent":False,"posted_at":ago(3)},
    {"title":"Library Card Renewal — Spring 2025","body":"Renew library cards at library office 9AM–1PM. Overdue books must be returned first.","category":"library","target":"all","is_urgent":False,"posted_at":ago(7)},
    {"title":"Attendance Warning — Below 75%","body":"Students below 75% attendance will not be allowed in exams. Contact teachers immediately.","category":"attendance","target":"all","is_urgent":True,"posted_at":ago(1)},
    {"title":"Revised Academic Calendar — Spring 2025","body":"Mid-terms: 5–12 May. Finals: 25 Jun – 5 Jul. Results: 20 July.","category":"academic","target":"all","is_urgent":False,"posted_at":ago(10)},
    {"title":"New AI Lab Inaugurated","body":"The new AI Research Lab has been inaugurated. AI and CS students can book lab slots.","category":"facilities","target":"department","departments":["CS","AI","SE"],"is_urgent":False,"posted_at":ago(6)},
    {"title":"Hostel Mess Fee Hike Notice","body":"Hostel mess fee has been revised from PKR 4,000 to PKR 5,000/month from May 2025.","category":"hostel","target":"hostel","is_urgent":False,"posted_at":ago(8)},
    {"title":"Campus Placement Drive — TechCorp","body":"TechCorp visiting campus on 2 May for placement interviews. CS/SE/AI students eligible.","category":"placement","target":"department","departments":["CS","SE","AI"],"is_urgent":False,"posted_at":ago(2)},
]
for a in announcements:
    a.update({"university":UNI_NAME,"posted_by":"Administration, IBA Sukkur","is_active":True})
    a.setdefault("departments",[])
db["announcements"].insert_many(announcements)
print(f"   ✅  {len(announcements)} announcements.\n")

# ════════════════════════════════════════════════════════════════════════
# 22. ROLES & PERMISSIONS
# ════════════════════════════════════════════════════════════════════════
print("🔑  Seeding roles & permissions...")
roles = [
    {
        "role":"student",
        "permissions":[
            "view_own_grades","view_own_attendance","view_own_assignments",
            "view_own_fees","view_own_exam_schedule","view_own_courses",
            "view_own_timetable","view_own_announcements","view_own_library",
            "view_own_scholarship","view_own_complaints","submit_complaint",
            "download_transcript","download_enrollment_certificate","download_fee_receipt",
            "download_admit_card"
        ],
        "fee_blocked_actions":["download_transcript","download_enrollment_certificate","download_admit_card"],
        "description":"Enrolled student — access to own academic & financial records"
    },
    {
        "role":"teacher",
        "permissions":[
            "view_own_courses","view_assigned_students","create_assignment",
            "grade_assignment","view_class_attendance","mark_attendance",
            "view_class_grades","upload_grades","view_exam_schedule",
            "create_exam_question","view_own_salary","view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"Faculty member — manage courses, grades, assignments"
    },
    {
        "role":"exam_staff",
        "permissions":[
            "view_all_exam_schedules","create_exam_schedule","issue_admit_cards",
            "block_admit_cards","view_all_students","view_grades","upload_results",
            "manage_seating_plans","view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"Examination department — manage exams and admit cards"
    },
    {
        "role":"finance_staff",
        "permissions":[
            "view_all_fees","update_fee_status","generate_challans",
            "issue_fee_receipts","view_scholarships","manage_scholarships",
            "view_salary_records","process_salaries","view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"Finance department — manage fees, challans, salaries"
    },
    {
        "role":"admission_staff",
        "permissions":[
            "view_all_students","create_student_profile","update_student_profile",
            "manage_enrollments","view_departments","view_courses",
            "issue_enrollment_certificates","view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"Admission office — manage student onboarding and enrollment"
    },
    {
        "role":"library_staff",
        "permissions":[
            "view_all_library_records","issue_books","return_books",
            "manage_fines","view_student_info","renew_library_cards",
            "view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"Library staff — manage book issuance and returns"
    },
    {
        "role":"hostel_staff",
        "permissions":[
            "view_hostel_records","manage_room_allotments","update_hostel_fees",
            "manage_hostel_complaints","view_student_info","view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"Hostel staff — manage hostel accommodation"
    },
    {
        "role":"admin_staff",
        "permissions":[
            "view_all_students","view_all_teachers","view_all_staff",
            "manage_announcements","view_complaints","resolve_complaints",
            "view_all_records","generate_reports","view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"Administrative staff — general university management"
    },
    {
        "role":"it_staff",
        "permissions":[
            "manage_users","reset_passwords","view_system_logs",
            "manage_database_backups","view_all_records","view_announcements"
        ],
        "fee_blocked_actions":[],
        "description":"IT staff — system and user management"
    },
    {
        "role": "superadmin",
        "permissions": ["all"],
        "fee_blocked_actions": [],
        "description": "Super administrator — full system access",
    },
]
db["roles"].insert_many(roles)
print(f"   ✅  {len(roles)} roles inserted.\n")

# ════════════════════════════════════════════════════════════════════════
# 23. CHAT LOGS
# ════════════════════════════════════════════════════════════════════════
db["chat_logs"].create_index([("student_id",ASCENDING),("created_at",DESCENDING)])

# ════════════════════════════════════════════════════════════════════════
# 24. RELATIONSHIP TABLES
# ════════════════════════════════════════════════════════════════════════
print("🔗  Seeding relationship tables...")

# ── Build lookup: course_code → teacher doc ──────────────────────────
teacher_by_course_code = {}   # "CS301" → {_id, full_name, employee_id, ...}
for fn,un,pw,dept,desig,role,courses_str in teachers_raw:
    tid = teacher_ids[un]
    for cc in [c.strip() for c in courses_str.split(",") if c.strip()]:
        teacher_by_course_code[cc] = {
            "teacher_id": tid, "teacher_name": fn,
            "department": dept, "designation": desig,
        }

# ── 24a. course_teacher_map ─────────────────────────────────────────
#    One doc per course: who teaches it + all enrolled student IDs
course_teacher_rows = []
for cc, cid in course_ids.items():
    t = teacher_by_course_code.get(cc)
    enrolled_sids = [
        e["student_id"]
        for e in enrollments
        if e["course_code"] == cc
    ]
    course_teacher_rows.append({
        "course_id": cid, "course_code": cc,
        "teacher_id": t["teacher_id"] if t else None,
        "teacher_name": t["teacher_name"] if t else None,
        "department": t["department"] if t else None,
        "enrolled_student_ids": enrolled_sids,
        "enrolled_count": len(enrolled_sids),
        "university": UNI_NAME,
    })
db["course_teacher_map"].insert_many(course_teacher_rows)
print(f"   ✅  {len(course_teacher_rows)} course_teacher_map rows.")

# ── 24b. teacher_student_relations ──────────────────────────────────
#    One doc per unique (teacher, student) pair — linked through courses
pairs_seen = set()
teacher_student_rows = []
for cc, t in teacher_by_course_code.items():
    cid = course_ids.get(cc)
    if not cid: continue
    for e in enrollments:
        if e["course_code"] != cc: continue
        sid = e["student_id"]
        key = (str(t["teacher_id"]), str(sid))
        if key in pairs_seen:
            # just append course to existing row later via update
            for row in teacher_student_rows:
                if str(row["teacher_id"]) == key[0] and str(row["student_id"]) == key[1]:
                    row["shared_courses"].append(cc)
                    break
            continue
        pairs_seen.add(key)
        # find student profile
        sp = student_profiles.get(str(sid), {})
        teacher_student_rows.append({
            "teacher_id": t["teacher_id"],
            "teacher_name": t["teacher_name"],
            "teacher_department": t["department"],
            "student_id": sid,
            "student_name": sp.get("full_name", ""),
            "student_department": sp.get("department", ""),
            "student_semester": sp.get("semester", 0),
            "shared_courses": [cc],
            "university": UNI_NAME,
        })
if teacher_student_rows:
    db["teacher_student_relations"].insert_many(teacher_student_rows)
print(f"   ✅  {len(teacher_student_rows)} teacher_student_relations rows.")

# ── 24c. student_course_teachers ────────────────────────────────────
#    One doc per unique (student, course) — includes who teaches it
student_course_teacher_rows = []
for e in enrollments:
    sid = e["student_id"]
    cc  = e["course_code"]
    cid = e["course_id"]
    t   = teacher_by_course_code.get(cc)
    sp  = student_profiles.get(str(sid), {})
    student_course_teacher_rows.append({
        "student_id": sid,
        "student_name": sp.get("full_name", ""),
        "student_department": sp.get("department", ""),
        "student_semester": sp.get("semester", 0),
        "course_id": cid,
        "course_code": cc,
        "teacher_id": t["teacher_id"] if t else None,
        "teacher_name": t["teacher_name"] if t else None,
        "university": UNI_NAME,
    })
if student_course_teacher_rows:
    db["student_course_teachers"].insert_many(student_course_teacher_rows)
print(f"   ✅  {len(student_course_teacher_rows)} student_course_teachers rows.\n")

# ════════════════════════════════════════════════════════════════════════
# 25. INDEXES
# ════════════════════════════════════════════════════════════════════════
print("🔍  Creating indexes...")
db["users"].create_index("username", unique=True)
db["users"].create_index("email",    unique=True)
db["students"].create_index("roll_number", unique=True)
db["students"].create_index([("department",1),("semester",1)])
db["teachers"].create_index("employee_id", unique=True)
db["enrollments"].create_index([("student_id",1),("semester",1)])
db["grades"].create_index([("student_id",1),("semester",1)])
db["fees"].create_index([("student_id",1),("semester",1)])
db["challans"].create_index("challan_number", unique=True)
db["assignment_submissions"].create_index([("student_id",1),("assignment_id",1)])
db["attendance"].create_index([("student_id",1),("course_id",1)])
db["admit_cards"].create_index([("student_id",1),("exam_id",1)])
db["transcripts"].create_index([("student_id",1)])
db["salaries"].create_index([("employee_id",1),("month",1)])
# Relationship table indexes
db["course_teacher_map"].create_index("course_code", unique=True)
db["course_teacher_map"].create_index("teacher_id")
db["teacher_student_relations"].create_index([("teacher_id",1),("student_id",1)])
db["teacher_student_relations"].create_index("student_id")
db["student_course_teachers"].create_index([("student_id",1),("course_code",1)])
db["student_course_teachers"].create_index("teacher_id")
print("   ✅  Indexes created.\n")

# ════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ════════════════════════════════════════════════════════════════════════
print("=" * 60)
print(f"✅  IBA SUKKUR DATABASE SEED COMPLETE")
print("=" * 60)
cols = ["users","students","teachers","staff","departments","courses",
        "enrollments","assignments","assignment_submissions","grades",
        "semester_results","fees","challans","attendance","timetable",
        "exams","admit_cards","transcripts","certificates","complaints",
        "library","scholarships","hostel","salaries","announcements","roles",
        "course_teacher_map","teacher_student_relations","student_course_teachers"]
print(f"\n{'Collection':<30} {'Documents':>10}")
print("-"*42)
for c in cols:
    print(f"  {c:<28} {db[c].count_documents({}):>10,}")

print(f"""
{'='*60}
🌐  University  : {UNI_NAME} (iba-suk.edu.pk)
📦  Database    : {DB_NAME}
🌐  Mongo URI   : {MONGO_URI}

👤  CREDENTIALS
{'─'*60}
  superadmin       / SuperAdmin@123   → role superadmin (JWT + portal)
  gmshaikn         / Prof@123!        → teacher (CS HOD)
  tmahmood         / Prof@123!        → teacher (AI HOD)
  kmehmood         / Prof@123!        → teacher (BBA HOD)
  msaleem          / Staff@123        → admin_staff
  jasoomro         / Staff@123        → exam_staff
  grasool          / Staff@123        → finance_staff
  tjamali          / Staff@123        → admission_staff
  myousuf          / Staff@123        → library_staff
  rhussain         / Staff@123        → hostel_staff

  All students     / Student@123      → student role

🧪  TEST SCENARIOS:
  • Students with unpaid fees → admit cards & transcripts blocked
  • Assignments with overdue status → flagged in submissions
  • Attendance < 75% → critical warning
  • Salary pending records → finance testing
  • Hostel students with room allotments
  • 20 collections covering every university workflow
{'='*60}
""")
client.close()