from __future__ import annotations
import os
from typing import Optional

def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch env var trying both UNDER_SCORE and DOT.SEPARATED names."""
    return os.getenv(key) or os.getenv(key.replace("_", "."), default)

class settings:
    """Central config.
    Important S3 envs:
      - S3_ENDPOINT: internal endpoint for SDK (e.g. http://minio:9000) — used by the app in Docker network.
      - S3_PUBLIC_ENDPOINT: external/public base URL for links (e.g. https://10.4.4.2). Can include scheme http/https.
        If not set, falls back to S3_ENDPOINT.
      Buckets can be set via either S3_BUCKET_* or S3.BUCKET_* names.
    """
    # Core
    # Use psycopg3 driver by default to match dependencies
    DB_URL = _env("DB_URL") or _env("DB.URL") or "postgresql+psycopg://postgres:postgres@postgres:5432/app"
    REDIS_URL = _env("REDIS_URL") or _env("REDIS.URL") or "redis://redis:6379/0"
    QDRANT_URL = _env("QDRANT_URL") or _env("QDRANT.URL") or "http://qdrant:6333"
    LLM_URL = _env("LLM_URL") or _env("LLM.URL") or "http://llm:8002"
    EMB_URL = _env("EMB_URL") or _env("EMB.URL") or "http://emb:8001"

    # Auth
    JWT_SECRET = os.getenv("JWT_SECRET")
    if not JWT_SECRET:
        import secrets
        JWT_SECRET = secrets.token_urlsafe(32)
        print("⚠️  WARNING: JWT_SECRET not set, using random secret. Set JWT_SECRET env var for production!")
    
    PASSWORD_PEPPER = os.getenv("PASSWORD_PEPPER", "")
    if not PASSWORD_PEPPER:
        import secrets
        PASSWORD_PEPPER = secrets.token_urlsafe(32)
        print("⚠️  WARNING: PASSWORD_PEPPER not set, using random pepper. Set PASSWORD_PEPPER env var for production!")
    
    ACCESS_TTL_SECONDS = int(os.getenv("ACCESS_TTL_SECONDS", "900"))  # 15 минут вместо 1 часа
    REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "7"))  # 7 дней вместо 30
    REFRESH_ROTATING = (str(os.getenv("REFRESH_ROTATING", "true")).lower() in ("1","true","yes"))

    # S3 / MinIO
    S3_ENDPOINT = _env("S3_ENDPOINT") or _env("S3.ENDPOINT") or "http://minio:9000"
    S3_PUBLIC_ENDPOINT = _env("S3_PUBLIC_ENDPOINT") or _env("S3.PUBLIC_ENDPOINT") or S3_ENDPOINT
    S3_ACCESS_KEY = _env("S3_ACCESS_KEY") or _env("S3.ACCESS_KEY") or "minio"
    S3_SECRET_KEY = _env("S3_SECRET_KEY") or _env("S3.SECRET_KEY") or "minio123"

    S3_BUCKET_RAG = _env("S3_BUCKET_RAG") or _env("S3.BUCKET_RAG") or "rag"
    S3_BUCKET_ANALYSIS = _env("S3_BUCKET_ANALYSIS") or _env("S3.BUCKET_ANALYSIS") or "analysis"

    # Email (optional)
    EMAIL_ENABLED = (os.getenv("EMAIL_ENABLED", "false").lower() in ("1", "true", "yes"))
    SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = (os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"))
    FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@ml-portal.local")
    
    # Password policy
    PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "12"))
    PASSWORD_REQUIRE_UPPERCASE = (os.getenv("PASSWORD_REQUIRE_UPPERCASE", "true").lower() in ("1", "true", "yes"))
    PASSWORD_REQUIRE_LOWERCASE = (os.getenv("PASSWORD_REQUIRE_LOWERCASE", "true").lower() in ("1", "true", "yes"))
    PASSWORD_REQUIRE_DIGITS = (os.getenv("PASSWORD_REQUIRE_DIGITS", "true").lower() in ("1", "true", "yes"))
    PASSWORD_REQUIRE_SPECIAL = (os.getenv("PASSWORD_REQUIRE_SPECIAL", "true").lower() in ("1", "true", "yes"))
    PASSWORD_PEPPER = os.getenv("PASSWORD_PEPPER", "")
    
    # Rate limiting
    RATE_LIMIT_LOGIN_ATTEMPTS = int(os.getenv("RATE_LIMIT_LOGIN_ATTEMPTS", "10"))
    RATE_LIMIT_LOGIN_WINDOW = int(os.getenv("RATE_LIMIT_LOGIN_WINDOW", "60"))
    
    # CORS
    CORS_ENABLED = (os.getenv("CORS_ENABLED", "true").lower() in ("1", "true", "yes"))
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    CORS_ALLOW_CREDENTIALS = (os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() in ("1", "true", "yes"))
    
    # Authentication modes
    AUTH_MODE = os.getenv("AUTH_MODE", "bearer")  # "bearer" or "cookie"
    COOKIE_AUTH_ENABLED = (os.getenv("COOKIE_AUTH_ENABLED", "false").lower() in ("1", "true", "yes"))
    CSRF_ENABLED = (os.getenv("CSRF_ENABLED", "false").lower() in ("1", "true", "yes"))
    
    # Reader permissions
    ALLOW_READER_UPLOADS = (os.getenv("ALLOW_READER_UPLOADS", "false").lower() in ("1", "true", "yes"))
    
    # Debug mode
    DEBUG = (os.getenv("DEBUG", "false").lower() in ("1", "true", "yes"))
    
    # Health
    HEALTH_DEEP = (os.getenv("HEALTH_DEEP", "0") == "1")
