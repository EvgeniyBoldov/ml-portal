from __future__ import annotations
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict, field_validator, ValidationInfo

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
    JWT_ACCESS_TTL_MINUTES: int = Field(default=1440)  # 24 hours for comfortable work
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
    LLM_API_KEY: str | None = Field(default=None, description="API key for LLM provider", validate_default=True)
    LLM_DEFAULT_MODEL: str = Field(default="llama-3.1-8b-instant", description="Default model to use")
    LLM_TIMEOUT: int = Field(default=30, description="Request timeout in seconds")
    
    # Embedding (deprecated - moved to models table)
    # These are kept for backward compatibility during migration
    EMB_BASE_URL: str = Field(default="http://localhost:8001")
    EMB_MODELS: str = Field(default="all-MiniLM-L6-v2")  # Comma-separated list
    EMB_MODEL_ALIAS: str = Field(default="all-MiniLM-L6-v2")
    EMB_USE_MOCK: bool = Field(default=False)
    EMB_OFFLINE: bool = Field(default=True, description="Disallow network downloads for embedding models")
    EMB_CACHE_DIR: str = Field(default="/tmp/sentence_transformers")
    EMB_BATCH_SIZE: int = Field(default=128)
    EMB_MAX_WAIT_MS: int = Field(default=8)
    
    # Reranker (local service, not in models table)
    RERANK_SERVICE_URL: str = Field(default="http://rerank:8002", description="Reranker service URL")
    RERANK_MODEL: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2", description="Reranker model name")
    RERANK_ENABLED: bool = Field(default=True, description="Enable reranker service")
    
    # OCR (local service, future)
    OCR_SERVICE_URL: str = Field(default="http://ocr:8003", description="OCR service URL")
    OCR_ENABLED: bool = Field(default=False, description="Enable OCR service")
    
    # ASR / Speech-to-Text (local service, future)
    ASR_SERVICE_URL: str = Field(default="http://whisper:8004", description="ASR service URL")
    ASR_ENABLED: bool = Field(default=False, description="Enable ASR service")
    
    # HTTP
    HTTP_TIMEOUT_SECONDS: int = Field(default=30)
    HTTP_MAX_RETRIES: int = Field(default=2)
    TIMEOUT_SECONDS: int = Field(default=30)
    DB_SLOW_QUERY_LOG_ENABLED: bool = Field(default=True)
    DB_SLOW_QUERY_THRESHOLD_MS: int = Field(default=500)
    DB_SLOW_QUERY_TEXT_MAX_LEN: int = Field(default=1200)
    GLOBAL_RATE_LIMIT_ENABLED: bool = Field(default=True)
    GLOBAL_RATE_LIMIT_RPM: int = Field(default=240)
    GLOBAL_RATE_LIMIT_RPH: int = Field(default=2400)

    # Circuit Breaker
    CB_LLM_FAILURES_THRESHOLD: int = Field(default=5)
    CB_LLM_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_LLM_HALF_OPEN_MAX_CALLS: int = Field(default=1)
    CB_EMB_FAILURES_THRESHOLD: int = Field(default=5)
    CB_EMB_OPEN_TIMEOUT_SECONDS: float = Field(default=30.0)
    CB_EMB_HALF_OPEN_MAX_CALLS: int = Field(default=1)

    # S3/MinIO
    S3_ENDPOINT: str = Field(default="http://minio:9000")
    S3_PUBLIC_ENDPOINT: str | None = Field(default=None, description="Public S3 endpoint for presigned URLs (e.g. https://files.localhost:8443). If not set, S3_ENDPOINT is used.")
    S3_ACCESS_KEY: str = Field(default="minioadmin")
    S3_SECRET_KEY: str = Field(default="minioadmin123")
    S3_SECURE: bool = Field(default=False)
    S3_BUCKET_RAG: str = Field(default="rag")
    S3_BUCKET_ARTIFACTS: str = Field(default="artifacts")
    S3_BUCKET_CHAT_UPLOADS: str = Field(default="chat-uploads")
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

    # Credentials encryption
    CREDENTIALS_MASTER_KEY: str | None = Field(
        default=None, 
        description="Master key for encrypting tool credentials. Required in production."
    )
    CONFIRMATION_SECRET: str | None = Field(
        default=None,
        description="Secret for operation confirmation tokens",
    )
    CONFIRMATION_TTL_SECONDS: int = Field(
        default=300,
        description="TTL for operation confirmation tokens in seconds",
    )

    # MCP Credential Broker (ephemeral access token for secret resolution)
    MCP_CREDENTIAL_BROKER_ENABLED: bool = Field(
        default=False,
        description="Enable short-lived MCP credential access token flow instead of raw credential payload injection",
    )
    MCP_CREDENTIAL_TOKEN_TTL_SECONDS: int = Field(
        default=90,
        description="TTL for MCP credential access tokens in seconds",
    )
    MCP_CREDENTIAL_BROKER_AUDIENCE: str = Field(
        default="urn:ml-portal:mcp-credential-broker",
        description="JWT audience for MCP credential broker tokens",
    )
    MCP_CREDENTIAL_BROKER_BASE_URL: str = Field(
        default="http://api:8000",
        description="Base URL that MCP servers use to call credential broker resolve endpoint",
    )
    MCP_CREDENTIAL_BROKER_RESOLVE_PATH: str = Field(
        default="/api/v1/internal/mcp/credentials/resolve",
        description="Path to credential broker resolve endpoint",
    )

    # Runtime RBAC behavior
    RUNTIME_RBAC_ENFORCE_RULES: bool = Field(
        default=False,
        description="Enable DB-backed RBAC rule enforcement in runtime resolution",
    )
    RUNTIME_RBAC_ALLOW_UNDEFINED: bool = Field(
        default=False,
        description="Test mode: allow undefined tools/collections by default",
    )
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str, info: ValidationInfo) -> str:
        """Ensure JWT secret is not default in production"""
        env = info.data.get("ENV", "local")
        if env != "local" and v == "change-me-in-production":
            raise ValueError("JWT_SECRET must be set in non-local environments")
        return v

    @field_validator("LLM_API_KEY")
    @classmethod
    def validate_llm_api_key(cls, v: str | None, info: ValidationInfo) -> str:
        """Ensure LLM API key is set (except in local/dev)"""
        env = os.getenv("ENV", info.data.get("ENV", "local"))
        
        # Allow empty in local/dev, require in production
        if not v and env not in ["local", "development"]:
            raise ValueError("LLM_API_KEY must be set in production")
        
        return v or "dev-key-placeholder"

    @field_validator("S3_SECRET_KEY")
    @classmethod
    def validate_s3_secret(cls, v: str, info: ValidationInfo) -> str:
        """Ensure S3 secret is not default in production"""
        env = info.data.get("ENV", "local")
        if env != "local" and v == "minioadmin":
            raise ValueError("S3_SECRET_KEY must be set in non-local environments")
        return v

    @field_validator("CONFIRMATION_SECRET")
    @classmethod
    def validate_confirmation_secret(cls, v: str | None, info: ValidationInfo) -> str | None:
        env = str(info.data.get("ENV", "local") or "local").strip().lower()
        strict_envs = {"production", "prod", "staging"}
        secret = str(v or "").strip()
        if env in strict_envs and not secret:
            raise ValueError("CONFIRMATION_SECRET must be set in production-like environments")
        return secret or None


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def get_embedding_models() -> list[str]:
    """Get embedding model aliases from env (single-model preferred)."""
    settings = get_settings()
    single = (settings.EMB_MODEL_ALIAS or "").strip()
    if single:
        return [single]
    return [model.strip() for model in settings.EMB_MODELS.split(',') if model.strip()]


def get_model_path(model_alias: str) -> str | None:
    """Get model path for alias from environment variables."""
    single_alias = (os.getenv("EMB_MODEL_ALIAS") or "").strip()
    if single_alias and single_alias == model_alias:
        explicit = os.getenv("EMB_MODEL_PATH")
        if explicit:
            return explicit
    env_key_upper = f"EMB_MODEL_{model_alias.upper().replace('-', '_')}_PATH"
    env_key_legacy = f"EMB_MODEL_{model_alias.replace('-', '_')}_PATH"
    return os.getenv(env_key_upper) or os.getenv(env_key_legacy)


def get_model_parallelism(model_alias: str) -> int:
    """Get parallelism setting for given model alias."""
    single_alias = (os.getenv("EMB_MODEL_ALIAS") or "").strip()
    if single_alias and single_alias == model_alias:
        value = os.getenv("EMB_MODEL_PARALLELISM")
        if value:
            return int(value)
    env_key_upper = f"EMB_PARALLELISM_{model_alias.upper().replace('-', '_')}"
    env_key_legacy = f"EMB_PARALLELISM_{model_alias.replace('-', '_')}"
    return int(os.getenv(env_key_upper) or os.getenv(env_key_legacy) or "1")


def is_production() -> bool:
    """Check if running in production environment"""
    return get_settings().ENV == "production"


def is_local() -> bool:
    """Check if running in local development environment"""
    return get_settings().ENV == "local"
