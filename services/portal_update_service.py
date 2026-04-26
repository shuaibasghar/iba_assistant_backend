"""
Central, permission-checked portal writes (grades, deletes, future ops).

Destructive / critical operations require confirmed=true unless actor is superadmin.
All successful writes are audit-logged. Superadmin bypasses confirmation but is always audited.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from bson import ObjectId
from pymongo import MongoClient

from config import get_settings


def _db():
    s = get_settings()
    client = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    return client[s.mongodb_database]


def _resolve_submission(
    db,
    *,
    submission_id: str | None,
    assignment_id: str | None,
    student_roll: str | None,
) -> dict[str, Any] | None:
    if submission_id:
        try:
            sid = ObjectId(submission_id)
        except Exception:
            return None
        return db["assignment_submissions"].find_one({"_id": sid})
    if assignment_id and student_roll:
        try:
            aid = ObjectId(assignment_id)
        except Exception:
            return None
        roll = str(student_roll).strip()
        sub = db["assignment_submissions"].find_one(
            {"assignment_id": aid, "student_roll": roll}
        )
        if sub:
            return sub
        return db["assignment_submissions"].find_one(
            {
                "assignment_id": aid,
                "student_roll": {"$regex": f"^{re.escape(roll)}$", "$options": "i"},
            }
        )
    return None


def _assert_teacher_owns_submission(teacher_id: str, sub: dict) -> None:
    try:
        tid = ObjectId(teacher_id)
    except Exception:
        raise PermissionError("Invalid teacher")
    cbt = sub.get("teacher_id")
    if cbt is None:
        raise PermissionError("No teacher on submission record")
    try:
        if isinstance(cbt, ObjectId):
            ok = cbt == tid
        else:
            ok = ObjectId(str(cbt)) == tid
    except Exception:
        ok = str(cbt) == str(tid)
    if not ok:
        raise PermissionError("Not the instructor for this submission")


def _normalize_lookup(lookup: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    sid = (lookup.get("submission_id") or "").strip() or None
    aid = (lookup.get("assignment_id") or "").strip() or None
    roll = (lookup.get("student_roll") or "").strip() or None
    if sid and (aid or roll):
        raise ValueError("Provide submission_id OR assignment_id + student_roll, not both.")
    if not sid and not (aid and roll):
        raise ValueError("Provide submission_id, or assignment_id and student_roll.")
    return sid, aid, roll


def _merge_payload(payload: dict[str, Any], updates_json: str | None) -> dict[str, Any]:
    out = {k: v for k, v in payload.items() if v is not None}
    if updates_json and str(updates_json).strip():
        try:
            extra = json.loads(updates_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"updates_json must be valid JSON: {e}") from e
        if not isinstance(extra, dict):
            raise ValueError("updates_json must be a JSON object")
        out.update(extra)
    return out


def _op_assignment_submission_grade(
    actor_user_id: str,
    actor_role: str,
    lookup: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    db = _db()
    sid, aid, roll = _normalize_lookup(lookup)
    sub = _resolve_submission(
        db,
        submission_id=sid,
        assignment_id=aid,
        student_roll=roll,
    )
    if not sub:
        raise ValueError("Submission not found.")

    role = (actor_role or "").lower()
    if role != "superadmin":
        _assert_teacher_owns_submission(actor_user_id, sub)

    allowed = {"marks_obtained", "feedback"}
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise ValueError(f"Unknown fields for grade: {sorted(unknown)}. Allowed: {sorted(allowed)}")

    if "marks_obtained" not in payload:
        raise ValueError("marks_obtained is required for operation grade.")

    marks = payload["marks_obtained"]
    try:
        marks_f = float(marks)
    except (TypeError, ValueError):
        raise ValueError("marks_obtained must be a number") from None

    cap = float(sub.get("out_of") or 100)
    if marks_f < 0 or marks_f > cap:
        raise ValueError(f"marks_obtained must be between 0 and {int(cap)} for this task.")

    st = str(sub.get("status") or "")
    if st == "pending":
        raise ValueError("Cannot grade a pending (not yet submitted) submission.")

    fb_raw = payload.get("feedback")
    fb = None
    if fb_raw is not None and str(fb_raw).strip():
        fb = str(fb_raw).strip()

    now = datetime.now(timezone.utc)
    db["assignment_submissions"].update_one(
        {"_id": sub["_id"]},
        {
            "$set": {
                "marks_obtained": marks_f,
                "feedback": fb,
                "graded": True,
                "graded_at": now,
            }
        },
    )

    return {
        "success": True,
        "entity": "assignment_submission",
        "operation": "grade",
        "submission_id": str(sub["_id"]),
        "assignment_id": str(sub["assignment_id"]),
        "student_name": sub.get("student_name"),
        "student_roll": sub.get("student_roll"),
        "marks_obtained": marks_f,
        "out_of": int(cap) if cap == int(cap) else cap,
        "feedback": fb,
        "graded_at": now.isoformat(),
    }


def _op_assignment_submission_delete(
    actor_user_id: str,
    actor_role: str,
    lookup: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    _ = actor_user_id, actor_role, payload
    db = _db()
    sid, aid, roll = _normalize_lookup(lookup)
    sub = _resolve_submission(
        db,
        submission_id=sid,
        assignment_id=aid,
        student_roll=roll,
    )
    if not sub:
        raise ValueError("Submission not found.")
    sub_oid = str(sub["_id"])
    rel = sub.get("submission_attachment_stored_name")
    if rel:
        from services.assignment_upload_service import get_submission_upload_dir

        p = get_submission_upload_dir() / str(rel)
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass
    db["assignment_submissions"].delete_one({"_id": sub["_id"]})
    return {
        "success": True,
        "entity": "assignment_submission",
        "operation": "delete",
        "deleted_submission_id": sub_oid,
    }


Handler = Callable[[str, str, dict[str, Any], dict[str, Any]], dict[str, Any]]

PORTAL_UPDATE_REGISTRY: dict[tuple[str, str], dict[str, Any]] = {
    ("assignment_submission", "grade"): {
        "roles": frozenset({"teacher", "superadmin"}),
        "handler": _op_assignment_submission_grade,
        "description": "Set marks_obtained, feedback; sets graded and graded_at.",
        "requires_confirmation": True,
    },
    ("assignment_submission", "delete"): {
        "roles": frozenset({"superadmin"}),
        "handler": _op_assignment_submission_delete,
        "description": "Permanently remove submission row and stored PDF (superadmin only).",
        "requires_confirmation": True,
    },
}


def portal_record_update(
    *,
    actor_role: str,
    actor_user_id: str,
    entity: str,
    operation: str,
    lookup: dict[str, Any],
    payload: dict[str, Any],
    updates_json: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """
    Dispatch a permission-checked portal update.

    If ``requires_confirmation`` is set for the operation and the actor is not
    ``superadmin``, returns a dict with ``needs_confirmation`` until ``confirmed`` is True.

    Raises PermissionError, ValueError when invalid.
    """
    role = (actor_role or "").strip().lower()
    uid = (actor_user_id or "").strip()
    if not uid:
        raise ValueError("actor_user_id is required")

    ent = (entity or "").strip().lower()
    op = (operation or "").strip().lower()
    key = (ent, op)
    if key not in PORTAL_UPDATE_REGISTRY:
        supported = [f"{e}.{o}" for e, o in PORTAL_UPDATE_REGISTRY]
        raise ValueError(
            f"Unsupported entity/operation '{entity}' / '{operation}'. "
            f"Supported: {', '.join(supported)}"
        )

    spec = PORTAL_UPDATE_REGISTRY[key]
    if role not in spec["roles"]:
        raise PermissionError(
            f"Role '{actor_role}' is not allowed for {entity}.{operation}. "
            f"Allowed roles: {sorted(spec['roles'])}"
        )

    is_super = role == "superadmin"
    req_conf = bool(spec.get("requires_confirmation", False))
    if req_conf and not is_super and not confirmed:
        return {
            "needs_confirmation": True,
            "are_you_sure_prompt": (
                "This action changes or removes important data. Ask the user clearly: "
                "\"Are you sure you want to proceed? (yes/no)\" and only continue if they answer yes. "
                "Then call this tool again with the same arguments and confirmed=true."
            ),
            "entity": ent,
            "operation": op,
            "lookup_summary": {k: v for k, v in lookup.items() if v},
        }

    merged = _merge_payload(payload, updates_json)
    handler: Handler = spec["handler"]
    result = handler(uid, role, lookup, merged)

    try:
        from services.audit_log_service import record_audit_event

        record_audit_event(
            actor_user_id=uid,
            actor_role=role,
            action="portal_record_update",
            entity=ent,
            operation=op,
            resource_type=ent,
            resource_id=result.get("submission_id") or result.get("deleted_submission_id"),
            summary=f"{ent}.{op}",
            detail={
                "lookup": {k: v for k, v in lookup.items() if v},
                "confirmation_bypassed": is_super and req_conf,
            },
            confirmation_bypassed=is_super and req_conf,
        )
    except Exception:
        pass

    return result


def list_portal_update_operations() -> list[dict[str, Any]]:
    out = []
    for (ent, op), spec in PORTAL_UPDATE_REGISTRY.items():
        out.append(
            {
                "entity": ent,
                "operation": op,
                "roles": sorted(spec["roles"]),
                "requires_confirmation": bool(spec.get("requires_confirmation", False)),
                "description": spec.get("description", ""),
            }
        )
    return out
