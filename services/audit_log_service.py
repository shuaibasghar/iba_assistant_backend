"""
Append-only audit trail for sensitive portal actions (especially superadmin and destructive ops).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient

from config import get_settings


def _db():
    s = get_settings()
    client = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    return client[s.mongodb_database]


def record_audit_event(
    *,
    actor_user_id: str,
    actor_role: str,
    action: str,
    entity: str | None = None,
    operation: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    summary: str | None = None,
    detail: dict[str, Any] | None = None,
    confirmation_bypassed: bool = False,
) -> None:
    """Persist one audit row. Failures are swallowed so business logic still completes."""
    try:
        db = _db()
        db["audit_logs"].insert_one(
            {
                "actor_user_id": str(actor_user_id),
                "actor_role": str(actor_role),
                "action": str(action),
                "entity": entity,
                "operation": operation,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "summary": summary,
                "detail": detail or {},
                "confirmation_bypassed": bool(confirmation_bypassed),
                "created_at": datetime.now(timezone.utc),
            }
        )
    except Exception:
        pass
