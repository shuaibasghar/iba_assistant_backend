"""
Database credentials API
========================
GET:  current config in the same shape the backend uses (passwords masked).
POST: test connections or apply new settings (runtime).
"""

import os
from typing import Any, Optional

import redis
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pymongo import MongoClient

from config import get_settings
from utils.db import mongodb_connector
from utils.db_credentials import mask_mongodb_url, mask_redis_url
from services.session_manager import get_session_manager
from services.auth import get_auth_service, UserAuth
from services.conversation_manager import ConversationManagerFactory

router = APIRouter(prefix="/database", tags=["Database"])


class DatabaseCredentialsFormat(BaseModel):
    """Documentation of fields expected by the backend (for frontend forms)."""
    mongodb_url: str = Field(
        description="MongoDB connection URI (mongodb:// or mongodb+srv://)",
        json_schema_extra={"example": "mongodb://localhost:27017"},
    )
    mongodb_database: str = Field(
        description="Database name",
        json_schema_extra={"example": "iba_suk_portal"},
    )
    redis_url: str = Field(
        description="Redis URL for sessions and chat history",
        json_schema_extra={"example": "redis://localhost:6379"},
    )
    session_ttl_seconds: int = Field(
        description="Session TTL in seconds (optional on apply)",
        json_schema_extra={"example": 1800},
    )


class DatabaseCredentialsPublic(BaseModel):
    """Safe view of current configuration (secrets masked)."""
    mongodb_url_masked: str
    mongodb_database: str
    redis_url_masked: str
    session_ttl_seconds: int
    format: dict[str, Any]


class DatabaseCredentialsTestRequest(BaseModel):
    """Payload to test DB connections (same shape as backend settings)."""
    mongodb_url: str
    mongodb_database: str
    redis_url: str = "redis://localhost:6379"


class DatabaseCredentialsTestResponse(BaseModel):
    ok: bool
    message: str
    mongodb_ping: bool = False
    redis_ping: bool = False
    sample_collections: list[str] = []


class DatabaseCredentialsApplyRequest(BaseModel):
    mongodb_url: str
    mongodb_database: str
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: Optional[int] = None


class DatabaseCredentialsApplyResponse(BaseModel):
    ok: bool
    message: str
    applied: dict[str, str]


async def _verify_apply_access(
    request: Request,
    x_setup_token: Optional[str] = Header(None, alias="X-Setup-Token"),
) -> UserAuth:
    """
    Apply allowed if:
    - settings.database_setup_token is set and matches X-Setup-Token, OR
    - Bearer token is a valid admin user.
    """
    settings = get_settings()
    if settings.database_setup_token and x_setup_token == settings.database_setup_token:
        return UserAuth(
            user_id="setup",
            email="setup@local",
            full_name="Setup",
            role="admin",
            department="",
        )

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Send X-Setup-Token (if configured) or Authorization: Bearer (admin)",
        )
    token = auth_header.split(" ", 1)[1]
    auth = get_auth_service()
    data = auth.verify_token(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = auth.get_user_by_id(data.user_id, data.role)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if data.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to apply DB config")
    return UserAuth(
        user_id=str(user["_id"]),
        email=user.get("email", ""),
        full_name=user.get("full_name", ""),
        role=data.role,
        department=user.get("department", ""),
    )


@router.get("/credentials", response_model=DatabaseCredentialsPublic)
async def get_database_credentials():
    """
    Return current database-related settings in the same field names the backend uses.
    Passwords in URLs are masked; use this to pre-fill the frontend form.
    """
    s = get_settings()
    return DatabaseCredentialsPublic(
        mongodb_url_masked=mask_mongodb_url(s.mongodb_url),
        mongodb_database=s.mongodb_database,
        redis_url_masked=mask_redis_url(s.redis_url),
        session_ttl_seconds=s.session_ttl_seconds,
        format={
            "fields": {
                "mongodb_url": "Full MongoDB connection string",
                "mongodb_database": "Database name",
                "redis_url": "Redis URL for sessions / chat history / token blacklist",
                "session_ttl_seconds": "Optional; session lifetime in seconds",
            },
            "example_request": DatabaseCredentialsTestRequest(
                mongodb_url="mongodb://localhost:27017",
                mongodb_database=s.mongodb_database,
                redis_url=s.redis_url,
            ).model_dump(),
        },
    )


@router.post("/credentials/test", response_model=DatabaseCredentialsTestResponse)
async def test_database_credentials(body: DatabaseCredentialsTestRequest):
    """
    Test MongoDB and Redis using the provided credentials (does not change server config).
    Use before apply to verify connections from the frontend form.
    """
    mongo_ok = False
    redis_ok = False
    sample_collections: list[str] = []
    try:
        sync_client = MongoClient(body.mongodb_url, serverSelectionTimeoutMS=5000)
        sync_client.admin.command("ping")
        mongo_ok = True
        db = sync_client[body.mongodb_database]
        sample_collections = db.list_collection_names()[:20]
        sync_client.close()
    except Exception as e:
        return DatabaseCredentialsTestResponse(
            ok=False,
            message=f"MongoDB error: {e!s}",
            mongodb_ping=mongo_ok,
            redis_ping=redis_ok,
        )

    try:
        r = redis.from_url(body.redis_url, decode_responses=True, socket_timeout=5)
        r.ping()
        redis_ok = True
        r.close()
    except Exception as e:
        return DatabaseCredentialsTestResponse(
            ok=False,
            message=f"Redis error: {e!s}",
            mongodb_ping=mongo_ok,
            redis_ping=redis_ok,
            sample_collections=sample_collections,
        )

    return DatabaseCredentialsTestResponse(
        ok=True,
        message="MongoDB and Redis connections successful",
        mongodb_ping=mongo_ok,
        redis_ping=redis_ok,
        sample_collections=sample_collections,
    )


@router.post("/credentials/apply", response_model=DatabaseCredentialsApplyResponse)
async def apply_database_credentials(
    body: DatabaseCredentialsApplyRequest,
    _auth: UserAuth = Depends(_verify_apply_access),
):
    """
    Apply new database settings to the running process (updates environment + reconnects).

    **Auth:** Either set `DATABASE_SETUP_TOKEN` in server env and send `X-Setup-Token`,
    or login as **admin** and use `Authorization: Bearer <token>`.

    Chat session caches are cleared; clients may need to log in again.
    """
    ttl = body.session_ttl_seconds
    if ttl is not None:
        os.environ["SESSION_TTL_SECONDS"] = str(ttl)
    os.environ["MONGODB_URL"] = body.mongodb_url
    os.environ["MONGODB_DATABASE"] = body.mongodb_database
    os.environ["REDIS_URL"] = body.redis_url

    get_settings.cache_clear()

    s = get_settings()
    try:
        await mongodb_connector.reconnect(s.mongodb_url, s.mongodb_database)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reconnect MongoDB: {e!s}")

    try:
        get_session_manager().reconfigure_connections(
            s.mongodb_url,
            s.mongodb_database,
            s.redis_url,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session manager reconfigure failed: {e!s}")

    try:
        get_auth_service().reconfigure_connections(
            s.mongodb_url,
            s.mongodb_database,
            s.redis_url,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth service reconfigure failed: {e!s}")

    ConversationManagerFactory.clear_all()

    return DatabaseCredentialsApplyResponse(
        ok=True,
        message="Database settings applied for this process. Persist MONGODB_URL / REDIS_URL in .env for restarts.",
        applied={
            "mongodb_url_masked": mask_mongodb_url(s.mongodb_url),
            "mongodb_database": s.mongodb_database,
            "redis_url_masked": mask_redis_url(s.redis_url),
            "session_ttl_seconds": str(s.session_ttl_seconds),
        },
    )
