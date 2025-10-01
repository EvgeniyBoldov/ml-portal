from functools import lru_cache
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    # HTTP
    HTTP_TIMEOUT_SECONDS: int = Field(30, env="HTTP_TIMEOUT_SECONDS")
    HTTP_MAX_RETRIES: int = Field(2, env="HTTP_MAX_RETRIES")

    # Upstreams
    LLM_BASE_URL: str = Field("http://localhost:8001", env="LLM_BASE_URL")
    EMB_BASE_URL: str = Field("http://localhost:8002", env="EMB_BASE_URL")
    QDRANT_URL: str = Field("http://localhost:6333", env="QDRANT_URL")

    # Object storage (S3/MinIO)
    S3_ENDPOINT: str = Field("localhost:9000", env="S3_ENDPOINT")
    S3_ACCESS_KEY: str = Field("minioadmin", env="S3_ACCESS_KEY")
    S3_SECRET_KEY: str = Field("minioadmin", env="S3_SECRET_KEY")
    S3_SECURE: bool = Field(False, env="S3_SECURE")

    class Config:
        env_file = ".env"

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
