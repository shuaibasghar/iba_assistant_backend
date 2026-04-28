import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from utils.db import mongodb_connector
from config import get_settings, get_backend_dir
from utils.agentops_setup import init_agentops

init_agentops()

from routers.chat import router as chat_router
from routers.auth import router as auth_router
from routers.report import router as report_router
from routers.assignments import router as assignments_router
from routers.upload import router as upload_router
from routers.whatsapp import router as whatsapp_router
from routers.exports import router as exports_router

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
    force=True,
)
log.info("Starting IBA Sukkur University Portal API")

def _display_mongo_target(url: str) -> str:
    """Host:port for logs (does not print user/password)."""
    p = urlsplit(url)
    if p.hostname:
        return f"{p.hostname}:{p.port}" if p.port else p.hostname
    return (p.netloc or url)[:80]


def _check_redis(url: str) -> None:
    r = redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        r.ping()
    finally:
        r.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start Mongo (Motor) and verify Redis. Configure via .env next to this app:
    MONGODB_URL, MONGODB_DATABASE, REDIS_URL
    """
    env_path = get_backend_dir() / ".env"
    print(
        f"[startup] Loading settings from: {env_path} (exists={env_path.is_file()})",
        flush=True,
    )
    settings = get_settings()
    try:
        await mongodb_connector.connect(settings.mongodb_url, settings.mongodb_database)
    except Exception as e:
        print(
            f"[startup] FATAL: MongoDB connection failed: {e!s}\n"
            f"  MONGODB_URL -> {_display_mongo_target(settings.mongodb_url)}\n"
            f"  MONGODB_DATABASE -> {settings.mongodb_database!r}",
            flush=True,
        )
        raise
    try:
        _check_redis(settings.redis_url)
    except Exception as e:
        print(
            f"[startup] FATAL: Redis ping failed: {e!s}\n"
            f"  REDIS_URL -> {settings.redis_url!r} — start Redis or fix REDIS_URL in .env",
            flush=True,
        )
        raise
    log.info("Data stores ready: MongoDB + Redis")
    print(
        "[startup] OK — database="
        f"{settings.mongodb_database!r} at {_display_mongo_target(settings.mongodb_url)} | Redis OK",
        flush=True,
    )

    yield

    await mongodb_connector.disconnect()


def _require_motor_db() -> None:
    if not mongodb_connector.is_motor_connected:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is not connected. Check MONGODB_URL and MONGODB_DATABASE in the server environment.",
        )


app = FastAPI(
    title="IBA Sukkur University Portal API",
    description="""
    AI-powered chatbot for university student and teacher queries.
    
    ## Authentication
    This API uses **JWT (JSON Web Token)** authentication with role-based access control.
    
    ### Roles
    - **Student**: Access to personal academic data (assignments, fees, grades, exams)
    - **Teacher**: Access to course management, student grades, attendance
    - **Admin**: Full system access
    
    ### How to Authenticate
    1. Call `POST /auth/login` with email and password
    2. Use the returned `access_token` in the Authorization header: `Bearer <token>`
    3. Token expires in 30 minutes - use `POST /auth/refresh` to get a new one
    4. Call `POST /auth/logout` to invalidate the token
    
    ### Demo Credentials
    Use any student/teacher email from the database with password: `password123`
    
    ## Features
    - Multi-agent system powered by CrewAI
    - Conversation memory with LangChain
    - Session management with Redis
    - Semantic search with ChromaDB
    - Role-based access control
    
    ## Supported Queries
    - Assignment status, due dates, submissions
    - Fee status, payment history
    - Exam schedules, venues
    - Academic grades, CGPA
    - Document requests
    
    ## Languages
    Supports English and Roman Urdu (e.g., "meri fees ka status batao")
    """,
    version="1.0.0",
    lifespan=lifespan, 
    swagger_ui_parameters={"persistAuthorization": True} # This is for the swagger UI to persist the authorization token
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(report_router)
app.include_router(assignments_router)
app.include_router(upload_router)
app.include_router(whatsapp_router)
app.include_router(exports_router)


@app.get("/")
async def root():
    return {"message": "University Data Analysis API is running"}


@app.get("/health")
async def health_check():
    settings = get_settings()
    motor_ok = mongodb_connector.is_motor_connected
    redis_ok = False
    try:
        r = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            redis_ok = r.ping()
        finally:
            r.close()
    except Exception:
        pass

    ok = motor_ok and redis_ok
    if ok:
        msg = "MongoDB (Motor) and Redis are reachable."
    else:
        issues = []
        if not motor_ok:
            issues.append("MongoDB (Motor) not connected — server may have failed to build the async client on startup")
        if not redis_ok:
            issues.append("Redis not reachable — start Redis or fix REDIS_URL")
        msg = " ".join(issues) + f" | env: {get_backend_dir() / '.env'}"
    return {
        "status": "healthy" if ok else "degraded",
        "message": msg,
        "mongodb": {
            "status": "connected" if motor_ok else "disconnected",
            "database": settings.mongodb_database if motor_ok else None,
        },
        "redis": {"status": "connected" if redis_ok else "disconnected"},
    }


@app.get("/schema")
async def get_database_schema():
    """Discover and return the complete database schema."""
    _require_motor_db()
    schema = await mongodb_connector.discover_full_schema()
    return schema


@app.get("/collections")
async def list_collections():
    """List all collections in the database."""
    _require_motor_db()
    collections = await mongodb_connector.list_collections()
    return {"collections": collections, "count": len(collections)}


@app.get("/collections/{collection_name}")
async def get_collection_info(collection_name: str):
    """Get schema information for a specific collection."""
    _require_motor_db()
    schema = await mongodb_connector.get_collection_schema(collection_name)
    return schema


@app.get("/collections/{collection_name}/records")
async def get_collection_records(
    collection_name: str, 
    limit: int = 10, 
    skip: int = 0
):
    """Fetch records from a specific collection."""
    _require_motor_db()
    records = await mongodb_connector.fetch_records(
        collection_name, 
        limit=limit, 
        skip=skip
    )
    return {"collection": collection_name, "records": records, "count": len(records)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
