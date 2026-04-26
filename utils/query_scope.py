"""
Detect how narrowly the student wants an answer (assignments, grades, etc.).
Used to inject hard constraints into CrewAI task text so the LLM cannot ignore them.
"""

from __future__ import annotations

import re

# ── Assignments ─────────────────────────────────────────────────────────────

ASSIGNMENT_SCOPE_PROMPTS: dict[str, str] = {
    "PENDING_ONLY": (
        "SYSTEM-LOCKED SCOPE: PENDING_ONLY.\n"
        "The user asked ONLY for assignments that are still pending (not submitted yet, due in the future).\n"
        "Rules you MUST follow:\n"
        "- Mention ONLY pending items. Do NOT write sections or bullets for overdue, submitted, or upcoming.\n"
        "- Do NOT write phrases like 'Overdue Assignments' or 'Submitted' at all.\n"
        "- If there are no pending items, say that in one short sentence.\n"
        "- Then optionally one line: offer to list overdue or submitted if they want."
    ),
    "OVERDUE_ONLY": (
        "SYSTEM-LOCKED SCOPE: OVERDUE_ONLY.\n"
        "Reply ONLY about overdue assignments. Do not mention pending, submitted, or upcoming."
    ),
    "CLOSEST_OVERDUE_ONLY": (
        "SYSTEM-LOCKED SCOPE: CLOSEST_OVERDUE_ONLY.\n"
        "The user asked which assignment is CLOSEST to overdue or about to be due.\n"
        "Rules you MUST follow:\n"
        "- Return ONLY the single assignment that is closest to its due date (most urgent).\n"
        "- Include ONLY: assignment name/title and course/subject name and due date.\n"
        "- Do NOT mention other assignments or previous submissions.\n"
        "- Do NOT say 'Make sure to submit', 'Keep it up', or add motivational phrases.\n"
        "- Format: A single short sentence like 'Your assignment closest to overdue is [Name] for [Course], due [Date].'"
    ),
    "SUBMITTED_ONLY": (
        "SYSTEM-LOCKED SCOPE: SUBMITTED_ONLY.\n"
        "Reply ONLY about submitted assignments (marks/feedback). Do not mention pending, overdue, or upcoming."
    ),
    "UPCOMING_ONLY": (
        "SYSTEM-LOCKED SCOPE: UPCOMING_ONLY.\n"
        "Reply ONLY about upcoming assignments. Do not mention pending, overdue, or submitted."
    ),
    "LAST_SUBMITTED_ONLY": (
        "SYSTEM-LOCKED SCOPE: LAST_SUBMITTED_ONLY.\n"
        "The user asked specifically for their LAST submitted assignment.\n"
        "Rules you MUST follow:\n"
        "- Return ONLY the most recent submitted assignment.\n"
        "- Include ONLY: assignment name/title and subject/course name.\n"
        "- Do NOT include marks, feedback, dates, or any other details.\n"
        "- Do NOT mention any other assignments or previous submissions.\n"
        "- Format: A single short sentence like 'Your last submitted assignment was [Name] for [Course].'"
    ),
    "NEWEST_INCOMPLETE_UPLOAD": (
        "SYSTEM-LOCKED SCOPE: NEWEST_INCOMPLETE_UPLOAD.\n"
        "The user asked for the LAST / LATEST / RECENT / NEWEST *pending* (not-yet-submitted) assignment.\n"
        "Rules you MUST follow:\n"
        "- Use **newest_incomplete_assignment** from the assignment tool — that is the task most recently "
        "**posted** on the portal (upload/created time), NOT the one with the nearest due date.\n"
        "- That row may be bucket pending, upcoming, or overdue; say so in one phrase if helpful.\n"
        "- If they asked for the PDF or link, include **assignment_brief_pdf_url** from that row (verbatim).\n"
        "- Answer in one short reply; do not list other assignments unless they asked for a full list.\n"
    ),
    "ALL": (
        "SYSTEM SCOPE: ALL.\n"
        "The user wants a full assignment picture. You may cover pending, overdue, submitted, and upcoming, "
        "but stay concise — no unnecessary repetition."
    ),
}


def detect_assignment_reply_scope(query: str) -> str:
    """
    Return PENDING_ONLY | OVERDUE_ONLY | SUBMITTED_ONLY | UPCOMING_ONLY | CLOSEST_OVERDUE_ONLY | LAST_SUBMITTED_ONLY | ALL
    based on English / Roman Urdu phrasing.
    """
    q = (query or "").lower().strip()
    if not q:
        return "ALL"

    # Check for "closest to overdue" / "about to due" patterns
    if re.search(r"\b(closest to overdue|about to due|close to overdue|due soon|nearing deadline|soonest due|next due)\b", q):
        return "CLOSEST_OVERDUE_ONLY"

    # Check for "last submitted" pattern
    if re.search(r"\blast\b.*\bsubmitted\b|\bsubmitted\b.*\blast\b|\blast\s+submission\b", q):
        return "LAST_SUBMITTED_ONLY"
    
    # Check for similar patterns: "most recent", "latest", "pichla" (previous in Urdu)
    if re.search(r"\b(most recent|latest|most recent submission|pichla submission|pichla assignment)\b", q):
        if re.search(r"\bsubmitted\b|\bsubmission\b", q):
            return "LAST_SUBMITTED_ONLY"

    # Last/latest/recent + pending = newest posted assignment not yet submitted (includes "upcoming" bucket)
    if re.search(r"\bpending\b", q) and not re.search(r"\bsubmitted\b|\bsubmission\b", q):
        if re.search(
            r"\b(last|latest|newest|recent|reece*nt|most recent|pichla|akhiri)\b",
            q,
        ) and not re.search(
            r"\b(all|everything|full|sab|list|kitne|how many|dikhao sab)\b",
            q,
        ):
            return "NEWEST_INCOMPLETE_UPLOAD"

    if re.search(r"\bpending\b", q) and re.search(r"\boverdue\b", q):
        return "ALL"
    if re.search(r"\bsubmitted\b", q) and re.search(r"\boverdue\b", q):
        return "ALL"

    has_narrow = bool(re.search(r"\b(only|just|sirf|bas)\b", q))
    has_pending = bool(re.search(r"\bpending\b", q))
    has_overdue = bool(re.search(r"\boverdue\b|\blate\b|\bmissed deadline\b", q))
    has_submitted = bool(re.search(r"\bsubmitted\b|\bmarks\b|\bfeedback\b", q))
    has_upcoming = bool(re.search(r"\bupcoming\b|\bdue later\b", q))

    if has_narrow and has_pending and not has_overdue and not has_submitted and not has_upcoming:
        return "PENDING_ONLY"

    if re.search(r"\bpending\s+assignments?\s+only\b", q) or re.search(
        r"\bassignments?\s+only\b", q
    ):
        if has_pending or "assignment" in q:
            if not has_overdue and not has_submitted and not has_upcoming:
                return "PENDING_ONLY"

    if has_narrow and has_overdue and not has_pending and not has_submitted:
        return "OVERDUE_ONLY"
    if has_narrow and has_submitted and not has_pending:
        return "SUBMITTED_ONLY"
    if has_narrow and has_upcoming and not has_pending:
        return "UPCOMING_ONLY"

    if re.search(r"\b(all|everything|full|complete|sab|poori|tafseel|detail)\b", q):
        return "ALL"

    if re.search(
        r"\b(pending\s+assignments?|mer[ae]y\s+pending|my\s+pending)\b",
        q,
    ):
        if (
            not has_overdue
            and not has_submitted
            and not has_upcoming
            and " and " not in q
        ):
            return "PENDING_ONLY"

    return "ALL"


def assignment_scope_prompt(scope: str) -> str:
    return ASSIGNMENT_SCOPE_PROMPTS.get(scope, ASSIGNMENT_SCOPE_PROMPTS["ALL"])


# ── Grades / CGPA ────────────────────────────────────────────────────────────

GRADE_SCOPE_PROMPTS: dict[str, str] = {
    "CGPA_ONLY": (
        "SYSTEM-LOCKED SCOPE: CGPA_ONLY.\n"
        "The user asked only for cumulative CGPA / GPA / pointer.\n"
        "Give the CGPA in one or two short sentences. Do NOT list courses, mid/final marks, or semester tables.\n"
        "Offer one line to share more if they want."
    ),
    "ALL": (
        "SYSTEM SCOPE: ALL.\n"
        "The user wants broader grade information; you may include courses and semesters as appropriate."
    ),
}


def detect_grade_reply_scope(query: str) -> str:
    q = (query or "").lower().strip()
    if not q:
        return "ALL"

    if re.search(
        r"\b(all grades|full transcript|every course|har subject|sab courses|breakdown|"
        r"each course|semester\s*[1-9]|sgpa\b.*\bsemester)\b",
        q,
    ):
        return "ALL"

    if re.search(
        r"\b(course|subject|cs[0-9]{3}|paper|marks for|mid-term|final exam)\b",
        q,
    ):
        return "ALL"

    if re.search(r"\bcgpa\b|\bcumulative\b.*\bgpa\b|\bgpa\b|\bpointer\b", q):
        return "CGPA_ONLY"

    return "ALL"


def grade_scope_prompt(scope: str) -> str:
    return GRADE_SCOPE_PROMPTS.get(scope, GRADE_SCOPE_PROMPTS["ALL"])
