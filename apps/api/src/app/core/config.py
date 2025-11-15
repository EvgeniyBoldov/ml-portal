from __future__ import annotations
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict, validator

class Settings(BaseSettings):
    # Environment
    ENV: str = Field(default="local")
    DEBUG: bool = Field(default=True)

    # Database
    DATABASE_URL: str = Field(default="postgresql://ml_portal:ml_portal_password@postgres:5432/ml_portal")
    ASYNC_DB_URL: str = Field(default="postgresql+asyncpg://ml_portal:ml_portal_password@postgres:5432/ml_portal")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # JWT - Asymmetric (RSA) for production, symmetric (HS256) for dev
    JWT_SECRET: str = Field(default="change-me-in-production", description="Symmetric secret for HS256 (dev only)")
    JWT_ALGORITHM: str = Field(default="HS256", description="HS256 for dev, RS256 for production")
    JWT_PRIVATE_KEY: str | None = Field(default=None, description="RSA private key (PEM format) for RS256")
    JWT_PUBLIC_KEY: str | None = Field(default=None, description="RSA public key (PEM format) for RS256")
    JWT_ISSUER: str = Field(default="urn:ml-portal")
    JWT_AUDIENCE: str = Field(default="urn:ml-portal:api")
    JWT_ACCESS_TTL_MINUTES: int = Field(default=15)
    JWT_REFRESH_TTL_DAYS: int = Field(default=30)
    JWT_KID: str | None = Field(default=None, description="Key ID for key rotation")

    # Authentication
    PAT_ENABLED: bool = Field(default=True)
    PASSWORD_MIN_LENGTH: int = Field(default=10)
    PASSWORD_REQUIRE_UPPERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_LOWERCASE: bool = Field(default=True)
    PASSWORD_REQUIRE_DIGITS: bool = Field(default=True)
    PASSWORD_REQUIRE_SPECIAL: bool = Field(default=False)
    PASSWORD_PEPPER: str | None = Field(default=None)

    # LLM - Universal configuration for any OpenAI-compatible provider
    # Supported providers: openai, groq, azure, local, vllm, ollama, etc.
    LLM_PROVIDER: str = Field(default="groq", description="LLM provider name (for logging/monitoring)")
    LLM_BASE_URL: str = Field(default="https://api.groq.com/openai/v1", description="OpenAI-compatible API base URL")
    LLM_API_KEY: str | None = Field(default=None, description="API key for LLM provider")
    LLM_DEFAULT_MODEL: str = Field(default="llama-3.1-8b-instant", description="Default model to use")
    LLM_TIMEOUT: int = Field(default=30, description="Request timeout in seconds")
    
    # Embedding
    EMB_BASE_URL: str = Field(default="http://localhost:8001")
    EMB_MODELS: str = Field(default="all-MiniLM-L6-v2")  # Comma-separated list
    EMB_MODEL_ALIAS: str = Field(default="all-MiniLM-L6-v2")
    EMB_USE_MOCK: bool = Field(default=False)
    EMB_OFFLINE: bool = Field(default=True, description="Disallow network downloads for embedding models")
    EMB_CACHE_DIR: str = Field(default="/tmp/sentence_transformers")
    EMB_BATCH_SIZE: int = Field(default=128)
    EMB_MAX_WAIT_MS: int = Field(default=8)
    
    # HTTP
    HTTP_TIMEOUT_SECONDS: int = Field(default=30)
    HTTP_MAX_RETRIES: int = Field(default=2)
    TIMEOUT_SECONDS: int = Field(default=30)

    # Circuit Breaker
    CB_LLM_FAILURES_THRESHOLD: int = Field(default=5)
    CB_LLM_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_LLM_HALF_OPEN_MAX_CALLS: int = Field(default=1)
    CB_EMB_FAILURES_THRESHOLD: int = Field(default=5)
    CB_EMB_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_EMB_HALF_OPEN_MAX_CALLS: int = Field(default=1)

    # S3/MinIO
    S3_ENDPOINT: str = Field(default="http://minio:9000")
    S3_ACCESS_KEY: str = Field(default="minioadmin")
    S3_SECRET_KEY: str = Field(default="minioadmin123")
    S3_SECURE: bool = Field(default=False)
    S3_BUCKET_RAG: str = Field(default="rag")
    S3_BUCKET_ARTIFACTS: str = Field(default="artifacts")
    SAVE_EMB_TO_S3: bool = Field(default=False)
    UPLOAD_MAX_BYTES: int = Field(default=100 * 1024 * 1024)
    UPLOAD_ALLOWED_MIME: str = Field(default="application/pdf,image/png,image/jpeg,application/octet-stream")

    # Qdrant
    QDRANT_URL: str = Field(default="http://localhost:6333")

    # Model Registry
    MODELS_ROOT: str = Field(default="/models_llm", description="Path to models directory")

    # Idempotency
    IDEMPOTENCY_ENABLED: bool = Field(default=True)
    IDEMP_TTL_HOURS: int = Field(default=24)
    IDEMPOTENCY_MAX_BYTES: int = Field(default=1_048_576)

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1")
    BEAT: int = Field(default=0)

    # CORS
    CORS_ALLOW_ORIGINS: str = Field(default="*")

    # Observability
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")
    PROMETHEUS_ENABLED: bool = Field(default=True)
    METRICS_PORT: int = Field(default=9090)

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    @validator("JWT_SECRET")
    def validate_jwt_secret(cls, v, values):
        """Ensure JWT secret is not default in production"""
        env = values.get("ENV", "local")
        if env != "local" and v == "change-me-in-production":
            raise ValueError("JWT_SECRET must be set in non-local environments")
        return v

    @validator("LLM_API_KEY", always=True)
    def validate_llm_api_key(cls, v, values):
        """Ensure LLM API key is set (except in local/dev)"""
        env = os.getenv("ENV", values.get("ENV", "local"))
        
        # Allow empty in local/dev, require in production
        if not v and env not in ["local", "development"]:
            raise ValueError("LLM_API_KEY must be set in production")
        
        return v or "dev-key-placeholder"

    @validator("S3_SECRET_KEY")
    def validate_s3_secret(cls, v, values):
        """Ensure S3 secret is not default in production"""
        env = values.get("ENV", "local")
        if env != "local" and v == "minioadmin":
            raise ValueError("S3_SECRET_KEY must be set in non-local environments")
        return v


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def get_embedding_models() -> list[str]:
    """Get list of embedding model aliases from EMB_MODELS"""
    settings = get_settings()
    return [model.strip() for model in settings.EMB_MODELS.split(',') if model.strip()]


def get_model_path(model_alias: str) -> str | None:
    """Get model path for given alias from environment variables"""
    env_key = f"EMB_MODEL_{model_alias.replace('-', '_')}_PATH"
    return os.getenv(env_key)


def get_model_parallelism(model_alias: str) -> int:
    """Get parallelism setting for given model alias"""
    env_key = f"EMB_PARALLELISM_{model_alias.replace('-', '_')}"
    return int(os.getenv(env_key, "1"))


def is_production() -> bool:
    """Check if running in production environment"""
    return get_settings().ENV == "production"


def is_local() -> bool:
    """Check if running in local development environment"""
    return get_settings().ENV == "local"
