"""
Baseline model - системные ограничения и правила для агентов.

Baseline отличается от Prompt:
- Scope-based: default → tenant → user (с наследованием)
- Содержит ограничения и запреты (что нельзя делать)
- Может быть привязан к агенту или применяться глобально
- Версионируется как Prompt

Примеры:
- default baseline: "Не генерируй код без явного запроса"
- tenant baseline: "Не упоминай конкурентов компании X"
- user baseline: "Всегда отвечай на русском языке"
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Boolean, DateTime, Text, Integer, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BaselineStatus(str, Enum):
    """Baseline version status"""
    DRAFT = "draft"        # Черновик - можно редактировать
    ACTIVE = "active"      # Активный - применяется к агентам
    ARCHIVED = "archived"  # Архивный - только для истории


class BaselineScope(str, Enum):
    """Baseline scope - уровень применения"""
    DEFAULT = "default"    # Глобальный - применяется ко всем
    TENANT = "tenant"      # Тенант - применяется к тенанту
    USER = "user"          # Пользователь - применяется к пользователю


class Baseline(Base):
    """
    Baseline container - holds metadata for baseline restrictions.
    
    A baseline is identified by a unique slug and contains:
    - name: Display name
    - description: Documentation
    - scope: default, tenant, or user
    - tenant_id/user_id: For scoped baselines
    
    Each baseline can have multiple versions (BaselineVersion).
    
    Resolution priority: User > Tenant > Default
    """
    __tablename__ = "baselines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Human-readable unique identifier (e.g., "security.no-code", "company.no-competitors")
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    # Display name for UI
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description for internal usage (MLOps documentation)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Scope: default, tenant, or user
    scope: Mapped[str] = mapped_column(
        String(20), 
        default=BaselineScope.DEFAULT.value, 
        nullable=False,
        index=True
    )
    
    # For tenant-scoped baselines
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    
    # For user-scoped baselines
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    
    # Whether this baseline is active
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
    
    # Relationship to versions
    versions: Mapped[List["BaselineVersion"]] = relationship(
        "BaselineVersion",
        back_populates="baseline",
        cascade="all, delete-orphan",
        order_by="desc(BaselineVersion.version)"
    )

    def __repr__(self):
        return f"<Baseline {self.slug} ({self.scope})>"


class BaselineVersion(Base):
    """
    Baseline version - holds template and version-specific data.
    
    Each version belongs to a Baseline and contains:
    - version: Sequential version number (1, 2, 3...)
    - template: Text content with restrictions
    - status: draft, active, or archived
    
    Only one version per baseline can be ACTIVE at a time.
    """
    __tablename__ = "baseline_versions"
    __table_args__ = (
        UniqueConstraint('baseline_id', 'version', name='uix_baseline_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Foreign key to baseline container
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('baselines.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # The baseline template content (plain text or Jinja2)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Sequential version number
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Version status: draft (editable), active (in use), archived (history)
    status: Mapped[str] = mapped_column(
        String(20), 
        default=BaselineStatus.DRAFT.value, 
        nullable=False,
        index=True
    )
    
    # Reference to parent version (for tracking version history)
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('baseline_versions.id', ondelete='SET NULL'),
        nullable=True
    )
    
    # Notes about this version (what changed)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
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
    baseline: Mapped["Baseline"] = relationship("Baseline", back_populates="versions")
    
    parent_version = relationship(
        "BaselineVersion", 
        remote_side=[id],
        backref="child_versions",
        foreign_keys=[parent_version_id]
    )

    @property
    def is_editable(self) -> bool:
        """Only draft versions can be edited"""
        return self.status == BaselineStatus.DRAFT.value
    
    @property
    def can_activate(self) -> bool:
        """Only draft versions can be activated"""
        return self.status == BaselineStatus.DRAFT.value

    def __repr__(self):
        return f"<BaselineVersion {self.baseline_id} v{self.version} ({self.status})>"
