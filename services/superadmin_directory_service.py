"""
Superadmin-only directory search and controlled writes for students, teachers, admins, and superadmins.

Whitelisted field updates; password / hash fields are never applied from chat. All mutations are audit-logged.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient

from config import get_settings

PROHIBITED_FIELD_SUBSTR = ("password", "hash", "secret", "bcrypt", "token")


def _db():
    s = get_settings()
    c = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    return c[s.mongodb_database]


DIRECTORY_COLLECTIONS: tuple[str, ...] = ("students", "teachers", "admins", "superadmins")

ALLOWED_UPDATE_FIELDS: dict[str, frozenset[str]] = {
    "students": frozenset(
        {
            "full_name",
            "email",
            "phone",
            "department",
            "roll_number",
            "semester",
            "batch",
            "status",
            "current_fee_status",
            "hostel",
            "cgpa",
        }
    ),
    "teachers": frozenset(
        {
            "full_name",
            "email",
            "phone",
            "department",
            "employee_id",
            "designation",
            "status",
            "assigned_course_codes",
        }
    ),
    "admins": frozenset(
        {
            "full_name",
            "email",
            "phone",
            "department",
            "employee_id",
            "role",
            "status",
        }
    ),
    "superadmins": frozenset(
        {
            "full_name",
            "email",
            "phone",
            "department",
            "employee_id",
            "designation",
            "status",
        }
    ),
}


def _email_variants(email: str) -> list[str]:
    e = (email or "").strip()
    if not e:
        return []
    return list(dict.fromkeys([e, e.lower()]))


def _summarize_row(collection: str, doc: dict) -> dict[str, Any]:
    oid = str(doc.get("_id", ""))
    out: dict[str, Any] = {
        "collection": collection,
        "document_id": oid,
        "full_name": doc.get("full_name"),
        "email": doc.get("email"),
    }
    if collection == "students":
        out["roll_number"] = doc.get("roll_number")
        out["semester"] = doc.get("semester")
        out["department"] = doc.get("department")
    elif collection in ("teachers", "admins", "superadmins"):
        out["employee_id"] = doc.get("employee_id")
        out["department"] = doc.get("department")
    return out


def _apply_name_filter(q: Any, col: str, query_parts: list[dict]) -> None:
    s = (str(q) if q is not None else "").strip()
    if not s:
        return
    esc = re.escape(" ".join(s.split()))
    query_parts.append({"full_name": {"$regex": esc, "$options": "i"}})


def _search(
    db,
    *,
    target_collection: str,
    match_document_id: str | None = None,
    match_full_name: str | None = None,
    match_email: str | None = None,
    match_roll_number: str | None = None,
    match_employee_id: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cols: list[str]
    if target_collection in DIRECTORY_COLLECTIONS:
        cols = [target_collection]
    else:
        cols = list(DIRECTORY_COLLECTIONS)

    if match_document_id and len(str(match_document_id)) == 24:
        try:
            oid = ObjectId(match_document_id)
        except (InvalidId, TypeError, ValueError):
            oid = None
        if oid is not None:
            for c in cols:
                doc = db[c].find_one({"_id": oid})
                if doc:
                    results.append(_summarize_row(c, doc))
            return results

    for c in cols:
        part_q: list[dict] = []
        and_parts: list[dict] = []
        if match_full_name is not None and str(match_full_name).strip():
            _apply_name_filter(match_full_name, c, and_parts)
        if match_email and str(match_email).strip():
            ems = _email_variants(str(match_email).strip())
            if ems:
                and_parts.append({"email": {"$in": ems}})
        if match_roll_number and c == "students" and str(match_roll_number).strip():
            r = str(match_roll_number).strip()
            and_parts.append(
                {
                    "roll_number": {
                        "$regex": f"^{re.escape(r)}$",
                        "$options": "i",
                    }
                }
            )
        if match_employee_id and c != "students" and str(match_employee_id).strip():
            eid = str(match_employee_id).strip()
            and_parts.append(
                {
                    "employee_id": {
                        "$regex": f"^{re.escape(eid)}$",
                        "$options": "i",
                    }
                }
            )

        if and_parts:
            part_q = [{"$and": and_parts}]

        if not part_q:
            continue
        for doc in db[c].find(part_q[0]).limit(limit - len(results)):
            results.append(_summarize_row(c, doc))
            if len(results) >= limit:
                return results
    return results


def _filter_updates(
    collection: str, raw: dict[str, Any]
) -> dict[str, Any]:
    allowed = ALLOWED_UPDATE_FIELDS.get(collection)
    if not allowed:
        raise ValueError(f"Unknown collection: {collection}")
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        low = k.lower()
        if any(p in low for p in PROHIBITED_FIELD_SUBSTR):
            continue
        if k in ("_id", "id"):
            continue
        if k not in allowed:
            raise ValueError(
                f"Field '{k}' is not allowed on {collection}. "
                f"Allowed: {sorted(allowed)}"
            )
        out[k] = v
    if not out:
        raise ValueError("No valid fields to update (after allowlist and security filter).")
    return out


def run_superadmin_directory_op(
    *,
    actor_user_id: str,
    actor_role: str,
    operation: str,
    target_collection: str = "auto",
    match_full_name: str | None = None,
    match_email: str | None = None,
    match_roll_number: str | None = None,
    match_employee_id: str | None = None,
    match_document_id: str | None = None,
    document_id: str | None = None,
    target_collection_for_id: str | None = None,
    updates: dict[str, Any] | None = None,
    updates_json: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    role = (actor_role or "").strip().lower()
    if role not in ("superadmin", "superuser"):
        raise PermissionError("Only superadmin may use this tool.")

    op = (operation or "").strip().lower()
    if op not in ("search", "update", "delete"):
        raise ValueError("operation must be one of: search, update, delete")

    db = _db()
    tcol = (target_collection or "auto").strip().lower()
    if tcol not in ("auto",) + DIRECTORY_COLLECTIONS:
        raise ValueError(
            f"target_collection must be auto or one of: {', '.join(DIRECTORY_COLLECTIONS)}"
        )

    merged: dict[str, Any] = {}
    if updates:
        merged.update(updates)
    if updates_json and str(updates_json).strip():
        try:
            j = json.loads(updates_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"updates_json must be valid JSON: {e}") from e
        if not isinstance(j, dict):
            raise ValueError("updates_json must be a JSON object")
        merged.update(j)

    # ——— search ———
    if op == "search":
        res = _search(
            db,
            target_collection=tcol,
            match_document_id=match_document_id or document_id,
            match_full_name=match_full_name,
            match_email=match_email,
            match_roll_number=match_roll_number,
            match_employee_id=match_employee_id,
        )
        return {
            "operation": "search",
            "count": len(res),
            "matches": res,
            "note": "If one row matches, use its collection and document_id for update/delete.",
        }

    # Direct id path for update/delete
    doc_oid: ObjectId | None = None
    dcol: str | None = None
    ex_id = (document_id or match_document_id or "").strip()
    t_for_id = (target_collection_for_id or "").strip().lower()
    if ex_id and t_for_id in DIRECTORY_COLLECTIONS:
        try:
            doc_oid = ObjectId(ex_id)
        except (InvalidId, TypeError, ValueError):
            doc_oid = None
        if doc_oid is not None:
            dcol = t_for_id
    if doc_oid is None or dcol is None:
        res = _search(
            db,
            target_collection=tcol,
            match_document_id=ex_id,
            match_full_name=match_full_name,
            match_email=match_email,
            match_roll_number=match_roll_number,
            match_employee_id=match_employee_id,
            limit=10,
        )
        if not res:
            return {
                "error": "No matching person found. Use operation=search with the same name/email fields, or pass document_id + target_collection_for_id.",
                "matches": [],
            }
        if len(res) > 1:
            return {
                "error": "Multiple matches. Ask the user which record, or narrow with email, roll, or employee_id.",
                "matches": res,
            }
        dcol = res[0]["collection"]
        try:
            doc_oid = ObjectId(res[0]["document_id"])
        except Exception as e:  # noqa: BLE001
            raise ValueError("Invalid document_id from search") from e

    assert dcol is not None and doc_oid is not None
    current = db[dcol].find_one({"_id": doc_oid})
    if not current:
        return {"error": f"Document not found in {dcol}", "document_id": str(doc_oid)}

    if op == "delete":
        if not confirmed:
            return {
                "needs_confirmation": True,
                "are_you_sure_prompt": (
                    "This permanently removes the profile document from the directory. "
                    "Ask: Are you sure? (yes/no) then call again with confirmed=true."
                ),
                "target_collection": dcol,
                "document_id": str(doc_oid),
                "summary": _summarize_row(dcol, current),
            }
        db[dcol].delete_one({"_id": doc_oid})
        _audit(actor_user_id, "delete", dcol, str(doc_oid), {"lookup": "directory"})
        return {
            "success": True,
            "operation": "delete",
            "target_collection": dcol,
            "document_id": str(doc_oid),
            "deleted": _summarize_row(dcol, current),
        }

    # update
    if op == "update":
        filtered = _filter_updates(dcol, merged)
        db[dcol].update_one({"_id": doc_oid}, {"$set": filtered})
        updated = db[dcol].find_one({"_id": doc_oid}) or current
        _audit(actor_user_id, "update", dcol, str(doc_oid), {"set": filtered})
        return {
            "success": True,
            "operation": "update",
            "target_collection": dcol,
            "document_id": str(doc_oid),
            "applied": filtered,
            "record": _summarize_row(dcol, updated),
        }

    raise ValueError("Unsupported operation state")


def _audit(actor: str, op: str, col: str, rid: str, detail: dict) -> None:
    try:
        from services.audit_log_service import record_audit_event

        record_audit_event(
            actor_user_id=actor,
            actor_role="superadmin",
            action="superadmin_directory",
            entity=col,
            operation=op,
            resource_type=col,
            resource_id=rid,
            summary=f"directory.{op}",
            detail={**detail, "resource_id": rid},
            confirmation_bypassed=True,
        )
    except Exception:
        pass
