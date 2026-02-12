"""Model Registry SQLAlchemy model

New architecture:
- Only LLM and Embedding models in database (dynamic, changeable)
- OCR/ASR/Reranker are local services (configured via settings.py)
- External providers (OpenAI, Groq) for MVP
- Easy swap to local providers later
"""
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, Text, DateTime, func, JSON, Enum as SQLEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from .base import Base

if TYPE_CHECKING:
    from .tool_instance import ToolInstance


class ModelType(str, enum.Enum):
    """Model types stored in database"""
    LLM_CHAT = "llm_chat"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    OCR = "ocr"
    ASR = "asr"
    TTS = "tts"
    # Note: ocr, asr, reranker, vision are NOW in database (immutable)


class ModelStatus(str, enum.Enum):
    """Model availability status"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEPRECATED = "deprecated"
    MAINTENANCE = "maintenance"


class HealthStatus(str, enum.Enum):
    """Health check status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class Model(Base):
    """Model registry for LLM and Embedding models
    
    Stores configuration for external providers (OpenAI, Groq, etc.)
    or local providers (future: HuggingFace models in containers).
    
    Example:
        - llm.chat.default: Groq llama-3.1-70b
        - embed.default: OpenAI text-embedding-3-large
    """
    __tablename__ = "models"
    __table_args__ = {'extend_existing': True}
    
    # Identity
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias: Mapped[str] = mapped_column(String(100), unique=True, index=True, comment="Unique identifier (e.g. llm.chat.default)")
    name: Mapped[str] = mapped_column(String(255), comment="Human-readable name")
    
    # Type & Provider
    type: Mapped[ModelType] = mapped_column(SQLEnum(ModelType, name="model_type", create_type=True), index=True, comment="Model type")
    provider: Mapped[str] = mapped_column(String(50), comment="Provider name (openai, groq, local, etc.)")
    provider_model_name: Mapped[str] = mapped_column(String(255), comment="Model name at provider")
    
    # Instance (provider connection)
    instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK to tool_instances (provider connection)"
    )
    
    # Configuration
    extra_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Provider-specific config (temperature, dimensions, etc.)")
    
    # Status
    status: Mapped[ModelStatus] = mapped_column(
        SQLEnum(ModelStatus, name="model_status", create_type=True),
        default=ModelStatus.AVAILABLE,
        comment="Availability status"
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", comment="System model (cannot be deleted)")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="Is model enabled")
    default_for_type: Mapped[bool] = mapped_column(Boolean, default=False, comment="Default model for this type")
    
    # Health
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_status: Mapped[HealthStatus | None] = mapped_column(
        SQLEnum(HealthStatus, name="health_status", create_type=True),
        nullable=True
    )
    health_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    
    # Versioning (important for embeddings - reindex if version changes)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Model version (for tracking changes)")
    
    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    instance: Mapped[Optional["ToolInstance"]] = relationship(
        "ToolInstance",
        foreign_keys=[instance_id],
        lazy="joined"
    )
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="Soft delete")


# Backward compatibility alias (will be removed after migration)
ModelRegistry = Model
