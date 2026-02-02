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


class Prompt(Base):
    """
    Prompt container - holds metadata for a system prompt.
    
    A prompt is identified by a unique slug and contains:
    - name: Display name
    - description: Documentation
    - type: prompt or baseline
    
    Each prompt can have multiple versions (PromptVersion).
    
    Note: Baseline restrictions are now a separate entity (see baseline.py).
    """
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Human-readable unique identifier (e.g., "chat.rag.system", "agent.netbox.config_gen")
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    # Display name for UI
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description for internal usage (MLOps documentation)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Type: prompt (instructions) or baseline (restrictions)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="prompt")
    
    # Reference to recommended version (for UI display)
    recommended_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('prompt_versions.id', ondelete='SET NULL', use_alter=True),
        nullable=True,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    # Relationship to versions
    versions: Mapped[List["PromptVersion"]] = relationship(
        "PromptVersion",
        back_populates="prompt",
        cascade="all, delete-orphan",
        order_by="desc(PromptVersion.version)",
        foreign_keys="PromptVersion.prompt_id"
    )
    
    # Relationship to recommended version
    recommended_version: Mapped[Optional["PromptVersion"]] = relationship(
        "PromptVersion",
        foreign_keys=[recommended_version_id],
        post_update=True
    )

    def __repr__(self):
        return f"<Prompt {self.slug}>"


class PromptVersion(Base):
    """
    Prompt version - holds template and version-specific data.
    
    Each version belongs to a Prompt and contains:
    - version: Sequential version number (1, 2, 3...)
    - template: Jinja2 template content
    - status: draft, active, or archived
    - input_variables: Expected template variables
    - generation_config: Model configuration overrides
    
    Only one version per prompt can be ACTIVE at a time.
    """
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint('prompt_id', 'version', name='uix_prompt_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Foreign key to prompt container
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('prompts.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # The prompt template content (Jinja2 format)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Expected input variables for validation (e.g., ["query", "context"])
    input_variables: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    # Model configuration override (e.g., {"temperature": 0.2, "model": "gpt-4"})
    generation_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Sequential version number
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    
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
        ForeignKey('prompt_versions.id', ondelete='SET NULL'),
        nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    # Relationships
    prompt: Mapped["Prompt"] = relationship(
        "Prompt",
        back_populates="versions",
        foreign_keys=[prompt_id]
    )
    
    parent_version = relationship(
        "PromptVersion", 
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
        return f"<PromptVersion {self.prompt_id} v{self.version} ({self.status})>"
