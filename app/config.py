import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings(BaseSettings):
    APP_NAME: str = "RepoMind - RAG System"
    VERSION: str = "1.0.0"
    
    # Gemini Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
    GEMINI_TIMEOUT_SECONDS: float = 30.0
    GEMINI_MAX_RETRIES: int = 2
    
    # Security & Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "repomind-super-secret-key-neon-electric-2026-secure")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Network & Storage
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    STORAGE_DIR: Path = BASE_DIR / os.getenv("STORAGE_DIR", "repomind_data")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    
    # Search & Indexing
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "fast_local")
    CHUNK_SIZE_LINES: int = 60
    CHUNK_OVERLAP_LINES: int = 15
    HYBRID_ALPHA: float = 0.55  # 0.55 vector + 0.45 BM25

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "repos").mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "indices").mkdir(parents=True, exist_ok=True)
