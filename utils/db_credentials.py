"""Helpers for safely exposing database connection info to the frontend (masked)."""

from __future__ import annotations

import re


def mask_mongodb_url(url: str) -> str:
    """
    Mask password in a MongoDB URI. Leaves host and path visible.
    mongodb://user:secret@host:27017/db -> mongodb://user:****@host:27017/db
    """
    if not url or "@" not in url:
        return url or ""
    try:
        # Handle mongodb+srv://user:pass@cluster/...
        scheme_sep = "://"
        if scheme_sep not in url:
            return "****"
        scheme, rest = url.split(scheme_sep, 1)
        if "@" not in rest:
            return url
        last_at = rest.rfind("@")
        before_at = rest[:last_at]
        after_at = rest[last_at + 1 :]
        if ":" in before_at:
            user, _pwd = before_at.split(":", 1)
            return f"{scheme}{scheme_sep}{user}:****@{after_at}"
        return f"{scheme}{scheme_sep}****@{after_at}"
    except Exception:
        return "mongodb://****"


def mask_redis_url(url: str) -> str:
    """Mask password in redis://user:pass@host:6379/0 if present."""
    if not url or "@" not in url:
        return url or ""
    try:
        if "://" not in url:
            return "****"
        scheme, rest = url.split("://", 1)
        if "@" not in rest:
            return url
        last_at = rest.rfind("@")
        before_at = rest[:last_at]
        after_at = rest[last_at + 1 :]
        if ":" in before_at:
            user, _pwd = before_at.split(":", 1)
            return f"{scheme}://{user}:****@{after_at}"
        return f"{scheme}://****@{after_at}"
    except Exception:
        return "redis://****"
