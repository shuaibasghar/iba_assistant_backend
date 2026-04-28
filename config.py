from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load the .env that lives next to this file (avoids CWD issues when
# running `python main.py` from another folder or under uvicorn reload).
_BACKEND_DIR = Path(__file__).resolve().parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MongoDB: MONGODB_URL, MONGODB_DATABASE
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "iba_suk_portal"

    # Redis: REDIS_URL, SESSION_TTL_SECONDS
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 1800  # 30 minutes

    # ChromaDB Configuration
    chroma_persist_directory: str = "./chroma_db"
    chroma_collection_name: str = "university_docs"

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # AgentOps (https://agentops.ai) — optional tracing for CrewAI / LangChain
    agentops_api_key: str = ""
    # Long-lived servers: if sessions close too early per request, try True (see AgentOps docs).
    agentops_skip_auto_end_session: bool = False

    # CrewAI Plus (optional) — used by CrewaiPlatformTools e.g. Gmail send_email
    crewai_platform_integration_token: str = ""
    crewai_email_apps: str = "gmail"

    # LangChain Configuration
    langchain_verbose: bool = True
    crewai_verbose: bool = False
    max_chat_history: int = 10  # Keep last N messages in context

    # JWT Authentication Configuration
    jwt_secret_key: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Assignment PDF uploads (relative to backend directory)
    assignment_upload_subdir: str = "uploads/assignments"
    # Student submission PDFs (turned-in work)
    submission_upload_subdir: str = "uploads/submissions"
    assignment_max_upload_mb: int = 20
    # Public API base for absolute signed download URLs (chat/email/WhatsApp). Dev default localhost; set real URL in production.
    public_api_base_url: str = "http://localhost:8000"
    # Short-lived signed JWT for ?token= assignment *brief* downloads (hours)
    assignment_download_token_expire_hours: int = 168
    # Submitted-work PDFs (?token= on /assignments/submission/signed); often needs longer for faculty review
    submission_download_token_expire_hours: int = 336

    # Generic file receive (e.g. POST /upload) — any type, stored locally
    upload_receive_subdir: str = "uploads/received"
    generic_upload_max_mb: int = 200

    # Chat exports: CSV/TXT/PDF (relative to backend directory); signed ?token= links
    exports_subdir: str = "uploads/exports"
    export_download_token_expire_hours: int = 24

    # SMTP Email Configuration
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""          # Gmail App Password (not your login password)
    smtp_from_email: str = ""        # defaults to smtp_user if empty

    # WhatsApp Cloud API Configuration (Meta Business)
    whatsapp_api_token: str = ""              # Permanent / temporary access token
    whatsapp_phone_number_id: str = ""        # Phone Number ID from Meta dashboard
    whatsapp_verify_token: str = "iba-sukkur-whatsapp-verify"  # Webhook verify token (you pick this)
    whatsapp_api_version: str = "v21.0"       # Graph API version
    whatsapp_business_account_id: str = ""    # WABA ID (optional, for analytics)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def get_backend_dir() -> Path:
    return _BACKEND_DIR
