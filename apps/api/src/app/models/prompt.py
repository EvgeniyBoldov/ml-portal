import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Boolean, DateTime, Text, Integer, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PromptStatus(str, Enum):
    """Prompt version status"""
    DRAFT = "draft"        # Черновик - можно редактировать
    ACTIVE = "active"      # Активный - используется агентами
    ARCHIVED = "archived"  # Архивный - только для истории


class PromptType(str, Enum):
    """Prompt type"""
    PROMPT = "prompt"      # Обычный системный промпт
    BASELINE = "baseline"  # Ограничения и запреты (что нельзя делать)


class Prompt(Base):
    """
    Prompt template registry for LLM interactions.
    
    Structure:
    - Prompts are grouped by slug (e.g., "rag.system", "agent.netbox")
    - Each slug can have multiple versions (1, 2, 3...)
    - Only one version per slug can be ACTIVE at a time
    - Versions can be DRAFT (editable), ACTIVE (in use), or ARCHIVED (history)
    
    Types:
    - PROMPT: Regular system prompt with instructions
    - BASELINE: Restrictions and limitations (what NOT to do)
    """
    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint('slug', 'version', name='uix_slug_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Human-readable unique identifier (e.g., "chat.rag.system", "agent.netbox.config_gen")
    slug: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    
    # Display name for UI
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description for internal usage (MLOps documentation)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # The prompt template content (Jinja2 format)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Expected input variables for validation (e.g., ["query", "context"])
    input_variables: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    # Model configuration override (e.g., {"temperature": 0.2, "model": "gpt-4"})
    generation_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1)
    
    # Version status: draft (editable), active (in use), archived (history)
    status: Mapped[str] = mapped_column(
        String(20), 
        default=PromptStatus.DRAFT.value, 
        nullable=False,
        index=True
    )
    
    # Reference to parent version (for tracking version history)
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('prompts.id', ondelete='SET NULL'),
        nullable=True
    )
    
    # Classification: prompt (instructions) or baseline (restrictions)
    type: Mapped[str] = mapped_column(
        String(50), 
        default=PromptType.PROMPT.value, 
        nullable=False
    )
    
    # Legacy field - kept for backward compatibility during migration
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    # Relationship to parent version
    parent_version = relationship(
        "Prompt", 
        remote_side=[id],
        backref="child_versions",
        foreign_keys=[parent_version_id]
    )

    @property
    def is_editable(self) -> bool:
        """Only draft versions can be edited"""
        return self.status == PromptStatus.DRAFT.value
    
    @property
    def can_activate(self) -> bool:
        """Only draft versions can be activated"""
        return self.status == PromptStatus.DRAFT.value

    def __repr__(self):
        return f"<Prompt {self.slug} v{self.version} ({self.status})>"
