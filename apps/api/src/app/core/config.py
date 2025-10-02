from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    ENV: str = Field(default="local")
    DEBUG: bool = Field(default=True)

    DB_URL: str = Field(default="sqlite:///./dev.db")
    ASYNC_DB_URL: str = Field(default="sqlite+aiosqlite:///./dev.db")

    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    JWT_SECRET: str = Field(default="change-me")
    JWT_ALGORITHM: str = Field(default="HS256")  # Prefer RS256/PS256 in production
    JWT_ISSUER: str = Field(default="urn:app")
    JWT_AUDIENCE: str = Field(default="urn:app:api")
    JWT_ACCESS_TTL_MINUTES: int = Field(default=15)
    JWT_REFRESH_TTL_DAYS: int = Field(default=30)
    JWT_JWKS_JSON: str | None = Field(default=None)
    JWT_KID: str | None = Field(default=None)

    PAT_ENABLED: bool = Field(default=True)

    PASSWORD_MIN_LENGTH: int = Field(default=10)
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_DIGITS: bool = Field(default=True)
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=False)
    PASSWORD_PEPPER: str | None = Field(default=None)

    LLM_BASE_URL: str = Field(default="http://localhost:8002")
    EMB_BASE_URL: str = Field(default="http://localhost:8001")
    HTTP_TIMEOUT_SECONDS: int = Field(default=30)
    HTTP_MAX_RETRIES: int = Field(default=2)
    TIMEOUT_SECONDS: int = Field(default=30)

    CB_LLM_FAILURES_THRESHOLD: int = Field(default=5)
    CB_LLM_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_LLM_HALF_OPEN_MAX_CALLS: int = Field(default=1)
    CB_EMB_FAILURES_THRESHOLD: int = Field(default=5)
    CB_EMB_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_EMB_HALF_OPEN_MAX_CALLS: int = Field(default=1)

    S3_ENDPOINT: str = Field(default="minio:9000")
    S3_ACCESS_KEY: str = Field(default="minioadmin")
    S3_SECRET_KEY: str = Field(default="minioadmin123")
    S3_SECURE: bool = Field(default=False)
    S3_BUCKET_RAG: str = Field(default="rag")
    S3_BUCKET_ARTIFACTS: str = Field(default="artifacts")
    UPLOAD_MAX_BYTES: int = Field(default=100 * 1024 * 1024)
    UPLOAD_ALLOWED_MIME: str = Field(default="application/pdf,image/png,image/jpeg,application/octet-stream")

    QDRANT_URL: str = Field(default="http://qdrant:6333")

    IDEMPOTENCY_ENABLED: bool = Field(default=True)
    IDEMP_TTL_HOURS: int = Field(default=24)
    IDEMPOTENCY_MAX_BYTES: int = Field(default=1_048_576)

    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1")
    BEAT: int = Field(default=0)

    CORS_ALLOW_ORIGINS: str = Field(default="*")

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()
