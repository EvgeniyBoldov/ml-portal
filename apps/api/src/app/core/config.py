from __future__ import annotations
from functools import lru_cache
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    # ---- Environment ----
    ENV: str = Field(default="local")
    DEBUG: bool = Field(default=True)

    # ---- Database ----
    DB_URL: str = Field(default="sqlite:///./dev.db")
    ASYNC_DB_URL: str = Field(default="sqlite+aiosqlite:///./dev.db")

    # ---- Redis ----
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # ---- Auth / JWT ----
    JWT_SECRET: str = Field(default="change-me")  # HS fallback (dev only)
    JWT_ALGORITHM: str = Field(default="HS256")   # Prefer RS256/PS256 in prod
    JWT_ISSUER: str = Field(default="urn:app")
    JWT_AUDIENCE: str = Field(default="urn:app:api")
    JWT_ACCESS_TTL_MINUTES: int = Field(default=15)
    JWT_REFRESH_TTL_DAYS: int = Field(default=30)
    JWT_JWKS_JSON: str | None = Field(default=None)  # published JWKS (stringified)
    JWT_KID: str | None = Field(default=None)        # current signing kid (dev only)

    # ---- Personal Access Tokens (PAT) ----
    PAT_ENABLED: bool = Field(default=True)

    # ---- Password policy ----
    PASSWORD_MIN_LENGTH: int = Field(default=10)
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_DIGITS: bool = Field(default=True)
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=False)
    PASSWORD_PEPPER: str | None = Field(default=None)

    # ---- HTTP / Upstreams ----
    LLM_BASE_URL: str = Field(default="http://localhost:8001")
    EMB_BASE_URL: str = Field(default="http://localhost:8002")
    HTTP_TIMEOUT_SECONDS: int = Field(default=30)
    HTTP_MAX_RETRIES: int = Field(default=2)
    TIMEOUT_SECONDS: int = Field(default=30)

    # ---- Circuit breaker ----
    CB_LLM_FAILURES_THRESHOLD: int = Field(default=5)
    CB_LLM_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_LLM_HALF_OPEN_MAX_CALLS: int = Field(default=1)
    CB_EMB_FAILURES_THRESHOLD: int = Field(default=5)
    CB_EMB_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_EMB_HALF_OPEN_MAX_CALLS: int = Field(default=1)

    # ---- Object storage (MinIO/S3) ----
    S3_ENDPOINT: str = Field(default="minio:9000")
    S3_ACCESS_KEY: str = Field(default="minioadmin")
    S3_SECRET_KEY: str = Field(default="minioadmin")
    S3_SECURE: bool = Field(default=False)
    S3_BUCKET_RAG: str = Field(default="rag")
    S3_BUCKET_ARTIFACTS: str = Field(default="artifacts")
    UPLOAD_MAX_BYTES: int = Field(default=100 * 1024 * 1024)  # 100MB (match nginx)
    UPLOAD_ALLOWED_MIME: str = Field(default="application/pdf,image/png,image/jpeg,application/octet-stream")

    # ---- Vector DB ----
    QDRANT_URL: str = Field(default="http://qdrant:6333")

    # ---- Idempotency ----
    IDEMPOTENCY_ENABLED: bool = Field(default=True)
    IDEMP_TTL_HOURS: int = Field(default=24)
    IDEMPOTENCY_MAX_BYTES: int = Field(default=1_048_576)

    # ---- Celery ----
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1")
    BEAT: int = Field(default=0)

    # ---- CORS ----
    CORS_ALLOW_ORIGINS: str = Field(default="*")  # comma-separated

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()
