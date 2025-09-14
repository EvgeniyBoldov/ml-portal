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

    # Health
    HEALTH_DEEP = (os.getenv("HEALTH_DEEP", "0") == "1")
