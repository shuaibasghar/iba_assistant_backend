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


def check_user_permission(query: str, role: str) -> Optional[str]:
    rule = get_permission_rule_for_role(role)
    if rule.matches_denied_query(query):
        return rule.deny_message
    return None
