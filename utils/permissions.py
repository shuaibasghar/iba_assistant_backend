"""
Permission rules for user roles and prohibited query detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Pattern


@dataclass
class RolePermissionRule:
    role: str
    description: str
    allowed_subjects: List[str]
    denied_subjects: List[str]
    denied_patterns: List[Pattern]
    deny_message: str

    def matches_denied_query(self, query: str) -> bool:
        normalized = query.lower()
        return any(pattern.search(normalized) for pattern in self.denied_patterns)


COMMON_DENIED_PATTERNS: List[Pattern] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bsalary\b",
        r"\bpayroll\b",
        r"\bcompensation\b",
        r"\bpay slip\b",
        r"\bsalary slip\b",
        r"\bbasic pay\b",
        r"\bteacher(?:'s|s)? salary\b",
        r"\bsalary of \w+\b",
        r"\bcontact details\b",
        r"\bphone number\b",
        r"\bmobile number\b",
        r"\bwhatsapp number\b",
        r"\bemail address\b",
        r"\bpersonal email\b",
        r"\bhome address\b",
        r"\bbank account\b",
        r"\baccount number\b",
        r"\bprivate details\b",
        r"\bprivate info\b",
        r"\bpersonal info\b",
        r"\bcontact info\b",
        r"\bstudent grades of\b",
        r"\bgrades of another student\b",
        r"\bmarks of another student\b",
        r"\btranscript of another student\b",
        r"\bquestion about .* salary\b",
        r"\bhow much .* earns\b",
        r"\bwhat does .* earn\b",
        r"\bwhich should not be asked\b"
    ]
]

ROLE_PERMISSION_RULES: List[RolePermissionRule] = [
    RolePermissionRule(
        role="student",
        description="Students may access their own academic data but must not request sensitive personnel or private contact details.",
        allowed_subjects=[
            "assignments",
            "fees",
            "grades",
            "exams",
            "documents",
            "attendance",
            "timetable",
            "library",
            "scholarships",
            "hostel",
            "complaints",
            "announcements",
            "general"
        ],
        denied_subjects=[
            "teacher salary",
            "teacher contact",
            "private student info",
            "bank account",
            "personal email",
            "home address"
        ],
        denied_patterns=COMMON_DENIED_PATTERNS,
        deny_message=(
            "You are not authorized to access that information. "
            "Please contact the administration office for sensitive personnel or financial details."
        ),
    ),
    RolePermissionRule(
        role="teacher",
        description="Teachers may access classroom-related data, but requests for sensitive personal or payroll details are prohibited.",
        allowed_subjects=[
            "assignments",
            "grades",
            "attendance",
            "timetable",
            "students",
            "announcements",
            "email",
            "general"
        ],
        denied_subjects=[
            "other teacher salary",
            "other teacher contact",
            "student personal info",
            "bank account",
            "private details"
        ],
        denied_patterns=COMMON_DENIED_PATTERNS,
        deny_message=(
            "That request is restricted. You are not authorized to retrieve personal or salary information. "
            "Please use official HR channels or contact administration."
        ),
    ),
    RolePermissionRule(
        role="admin",
        description="Admins may access administrative portal data, but sensitive personnel and payroll questions should still be handled through official channels.",
        allowed_subjects=[
            "announcements",
            "reports",
            "system status",
            "students",
            "teachers",
            "general"
        ],
        denied_subjects=[
            "teacher salary",
            "personal contact",
            "private student info",
            "bank account",
            "passwords"
        ],
        denied_patterns=COMMON_DENIED_PATTERNS,
        deny_message=(
            "That query is restricted. Please contact HR or administration for sensitive personnel or payroll information."
        ),
    ),
]

ROLE_PERMISSION_MAP = {rule.role: rule for rule in ROLE_PERMISSION_RULES}

DEFAULT_ROLE_PERMISSION = RolePermissionRule(
    role="default",
    description="Default permissions for unknown roles.",
    allowed_subjects=[
        "general",
    ],
    denied_subjects=[
        "salary",
        "contact",
        "private info"
    ],
    denied_patterns=COMMON_DENIED_PATTERNS,
    deny_message=(
        "You are not authorized to access that information. "
        "Please contact the administration office for sensitive requests."
    ),
)


def get_permission_rule_for_role(role: str) -> RolePermissionRule:
    return ROLE_PERMISSION_MAP.get(role.lower(), DEFAULT_ROLE_PERMISSION)


def _is_student_bulk_directory_request(query: str) -> bool:
    """
    Full teacher/staff/faculty rosters, CSV/Excel lists, and similar directory exports
    for students. Handled with a one-line deny before intent routing.
    """
    n = re.sub(r"\s+", " ", (query or "").lower()).strip()
    if not n or len(n) < 6:
        return False
    if re.search(r"\b(all|every|entire|full|complete)\s+teachers?\b", n):
        return True
    if re.search(r"\bteachers?(\'s)?\s+(in|as|to)\s+(a\s+)?(csv|excel|spreadsheet)\b", n):
        return True
    if "csv" in n and re.search(
        r"\b(teacher|teachers|faculty|staff|employee|instructor)s?\b", n
    ) and re.search(
        r"\b(list|lists|roster|export|download|generate|get|show|give|bana|banaye)\b", n
    ):
        return True
    if re.search(r"\b(list|roster|directory) of (all|every|all the)\s+teachers?\b", n):
        return True
    if re.search(
        r"\b(list|roster|directory)\b", n
    ) and re.search(r"\b(all|every|full|entire|complete)\b", n) and re.search(
        r"\b(teacher|teachers|faculty|staff)\b", n
    ):
        return True
    if re.search(
        r"\b(names? of|name of) (all|every)\s+teachers?\b", n
    ) or re.search(
        r"\b(all|every) teachers? names?\b", n
    ):
        return True
    if re.search(
        r"\b(show|give|send|batao|batao na|yes|haan)\b", n
    ) and re.search(
        r"\b(all|every)\s+teac\w*\b", n
    ) and re.search(
        r"\b(name|names|list|csv)\b", n
    ):
        return True
    # Typo-tolerant: "all teacehrs name" without leading show/give/yes
    if "all" in n and re.search(
        r"\bteac\w+\b", n
    ) and re.search(r"\b(name|names|list|csv|show)\b", n):
        return True
    return False


# Single line, no long explanations (product policy for denied directory-style asks).
STUDENT_DIRECTORY_DENY = "You are not authorized to access that."


def check_user_permission(query: str, role: str) -> Optional[str]:
    r = (role or "").strip().lower()
    if r in ("superadmin", "superuser"):
        return None
    if r == "student" and _is_student_bulk_directory_request(query):
        return STUDENT_DIRECTORY_DENY
    rule = get_permission_rule_for_role(role)
    if rule.matches_denied_query(query):
        return rule.deny_message
    return None
