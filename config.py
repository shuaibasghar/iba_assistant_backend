from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # MongoDB Configuration
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "iba_suk_portal"
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 1800  # 30 minutes
    
    # Optional: if set, POST /database/credentials/apply accepts header X-Setup-Token
    # with this value (use for first-time setup when no admin session exists)
    database_setup_token: str = ""
    
    # ChromaDB Configuration
    chroma_persist_directory: str = "./chroma_db"
    chroma_collection_name: str = "university_docs"
    
    # OpenAI Configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    
    # LangChain Configuration
    langchain_verbose: bool = True
    max_chat_history: int = 10  # Keep last N messages in context
    
    # JWT Authentication Configuration
    jwt_secret_key: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
