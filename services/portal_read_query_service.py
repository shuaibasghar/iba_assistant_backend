"""
Generic read-only MongoDB queries (count / list) for portal staff, with safe query
documents—no $where, no code execution.

**Superadmin** may query **any** normal MongoDB collection name in the app database
(matching a safe identifier pattern). **Admin** is limited to READ_COLLECTIONS_ADMIN.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any

from bson import ObjectId
from bson.dbref import DBRef
from pymongo import MongoClient

from config import get_settings

# Admin: explicit allowlist (aligned with portal MongoDB collections).
# Superadmin: any name matching COLLECTION_NAME_RE (see _superadmin_may_read_collection).
READ_COLLECTIONS_ADMIN: frozenset[str] = frozenset(
    {
        "admit_cards",
        "admins",
        "announcements",
        "assignment_submissions",
        "assignments",
        "attendance",
        "certificates",
        "challans",
        "chat_logs",
        "complaints",
        "course_teacher_map",
        "courses",
        "departments",
        "enrollments",
        "exams",
        "fees",
        "grades",
        "hostel",
        "library",
        "roles",
        "salaries",
        "scholarships",
        "semester_results",
        "semesters",
        "staff",
        "student_course_teachers",
        "students",
        "superadmins",
        "teacher_student_relations",
        "teachers",
        "timetable",
        "transcripts",
        "users",
    }
)

# Superadmin: valid collection names [a-zA-Z_][a-zA-Z0-9_]* up to 64 chars.
COLLECTION_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
# Top-level field name for distinct (single segment only).
DISTINCT_FIELD_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Optional blocklist for superadmin (e.g. if a collection must never be read via chat).
SUPER_READ_DENY: frozenset[str] = frozenset()

REJECTED_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "$where",
        "$function",
        "$accumulator",
        "$expr",  # can exfil; disable for v1
        "$match",  # only in aggregate; if passed at top level, confusing
    }
)

STRIP_FROM_OUTPUT: frozenset[str] = frozenset(
    {"password", "password_hash", "bcrypt", "hashedPassword"}
)

MAX_LIMIT = 200
DEFAULT_LIMIT = 50
MAX_QUERY_JSON_LEN = 12_000


def _get_db():
    s = get_settings()
    c = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    return c[s.mongodb_database]


def _normalize_role(r: str) -> str:
    x = (r or "").strip().lower()
    return "superadmin" if x in ("superuser", "superadmin") else x


def _superadmin_may_read_collection(name: str) -> bool:
    n = (name or "").strip()
    if not COLLECTION_NAME_RE.fullmatch(n):
        return False
    if n in SUPER_READ_DENY:
        return False
    return True


def _validate_filter(q: Any, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("Query JSON is too deeply nested")
    if isinstance(q, list):
        for i in q:
            _validate_filter(i, depth + 1)
        return
    if not isinstance(q, dict):
        return
    for k, v in q.items():
        if k in REJECTED_QUERY_KEYS:
            raise ValueError(f"Query operator {k!r} is not allowed (security)")
        if k.startswith("$") and k not in (
            "$and",
            "$or",
            "$nor",
            "$not",
            "$in",
            "$nin",
            "$eq",
            "$ne",
            "$gt",
            "$gte",
            "$lt",
            "$lte",
            "$regex",
            "$options",
            "$exists",
            "$all",
            "$type",
        ):
            raise ValueError(
                f"Query operator {k!r} is not allowed. Use $and/$or, field equality, or $regex."
            )
        if isinstance(v, (dict, list)):
            _validate_filter(v, depth + 1)


def _parse_query_json(query_json: str | None) -> dict[str, Any]:
    if not query_json or not str(query_json).strip():
        return {}
    if len(str(query_json)) > MAX_QUERY_JSON_LEN:
        raise ValueError("query_json is too long")
    try:
        out = json.loads(str(query_json))
    except json.JSONDecodeError as e:
        raise ValueError(f"query_json must be valid JSON: {e}") from e
    if not isinstance(out, dict):
        raise ValueError("query_json must be a JSON object, e.g. {{\"department\": \"CS\"}}")
    _validate_filter(out)
    return out


def _serialize_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, (datetime, date)):
        if hasattr(v, "tzinfo") and v.tzinfo is None and isinstance(v, datetime):
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat() if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, DBRef):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return f"<{len(v)} bytes>"
    if isinstance(v, dict):
        return {k: _serialize_value(x) for k, x in v.items() if k not in STRIP_FROM_OUTPUT}
    if isinstance(v, list):
        return [_serialize_value(x) for x in v]
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def _sanitize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in doc.items():
        if k in STRIP_FROM_OUTPUT:
            continue
        if k == "_id":
            out["_id"] = str(v)
        else:
            out[k] = _serialize_value(v)
    return out


def run_portal_read_query(
    *,
    actor_user_id: str,
    actor_role: str,
    collection: str,
    operation: str,
    query_json: str | None = None,
    limit: int | None = None,
    sort_key: str | None = None,
    sort_dir: int = 1,
    distinct_field: str | None = None,
) -> dict[str, Any]:
    """
    count: return total matching filter.
    find: return up to `limit` documents (redacted, serialized).
    distinct: return sorted unique values for `distinct_field` (with optional filter).
    """
    _ = actor_user_id
    r = _normalize_role(actor_role)
    col = (collection or "").strip()
    op = (operation or "").strip().lower()
    if op not in ("count", "find", "distinct"):
        raise ValueError("operation must be 'count', 'find', or 'distinct'")

    if r not in ("superadmin", "admin"):
        raise PermissionError(
            "This query tool is for admin or superadmin. Ask an administrator, or rephrase for your own data."
        )
    if r == "superadmin":
        if not _superadmin_may_read_collection(col):
            raise ValueError(
                f"Invalid collection name {col!r}. Use the real MongoDB collection name "
                f"(e.g. `library` for book/issue records, not `library_system`). "
                f"Only letters, digits, and underscores."
            )
    else:
        if col not in READ_COLLECTIONS_ADMIN:
            raise ValueError(
                f"Collection {col!r} is not available for admin. "
                f"Use one of: {', '.join(sorted(READ_COLLECTIONS_ADMIN))}"
            )

    flt = _parse_query_json(query_json)
    db = _get_db()
    if col not in db.list_collection_names():
        return {
            "error": f"Collection {col!r} does not exist in this database.",
            "count": 0,
            "hint": "Check MongoDB or seed data (e.g. run dummy seed scripts).",
        }

    coll = db[col]

    if op == "distinct":
        df = (distinct_field or "").strip()
        if not df or not DISTINCT_FIELD_RE.fullmatch(df):
            raise ValueError(
                "operation 'distinct' requires distinct_field, e.g. 'role' for user roles, "
                "as a single field name (letters, digits, underscore)."
            )
        try:
            raw_vals = coll.distinct(df, flt)
        except Exception as e:
            raise ValueError(
                f"Distinct on {df!r} failed (field may not exist on this collection): {e}"
            ) from e
        # Stable, JSON-friendly ordering
        ser = _serialize_value(raw_vals)
        if not isinstance(ser, list):
            ser = [ser]
        str_sorted = sorted(ser, key=lambda x: (str(type(x)), str(x)))
        return {
            "ok": True,
            "operation": "distinct",
            "collection": col,
            "field": df,
            "query": flt,
            "n_distinct": len(str_sorted),
            "values": str_sorted,
            "message": f"Distinct {df!r} in {col!r}: {len(str_sorted)} unique value(s).",
        }

    if op == "count":
        n = int(coll.count_documents(flt))
        return {
            "ok": True,
            "operation": "count",
            "collection": col,
            "query": flt,
            "count": n,
            "message": f"Count for {col}: {n} document(s) matching the filter.",
        }

    # find
    lim = min(int(limit) if limit is not None else DEFAULT_LIMIT, MAX_LIMIT)
    sk = (sort_key or "").strip() or None
    direction = 1 if sort_dir >= 0 else -1
    cur = coll.find(flt)
    if sk:
        try:
            cur = cur.sort(sk, direction)
        except Exception as e:
            raise ValueError(f"Invalid sort: {e}") from e
    cur = cur.limit(lim)
    raw = list(cur)
    rows = [_sanitize_doc(d) for d in raw]
    return {
        "ok": True,
        "operation": "find",
        "collection": col,
        "query": flt,
        "returned": len(rows),
        "limit": lim,
        "rows": rows,
        "message": f"Retrieved {len(rows)} document(s) from {col!r} (max {lim}).",
    }
