"""
Tool Release Models - версионирование инструментов

ToolBackendRelease - версия из кода (заполняется воркером при старте)
ToolRelease - версия для использования агентами (как PromptVersion)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.tool import Tool


class ToolReleaseStatus(str, Enum):
    """Tool release status"""
    DRAFT = "draft"        # Можно редактировать, можно активировать
    ACTIVE = "active"      # Используется агентами (только один active на tool)
    ARCHIVED = "archived"  # Только для истории


class ToolBackendRelease(Base):
    """
    Версия инструмента из кода.
    
    Заполняется автоматически при старте воркера путём сканирования
    классов VersionedTool и их методов с декоратором @tool_version.
    
    НЕ редактируется через UI - только просмотр.
    """
    __tablename__ = "tool_backend_releases"
    
    __table_args__ = (
        UniqueConstraint('tool_id', 'version', name='uq_tool_backend_release_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Семантическая версия из кода (e.g., "1.0.0", "2.1.0")
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # JSON Schema для входных параметров
    input_schema: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # JSON Schema для выходных данных
    output_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Описание версии (из docstring или description в декораторе)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Имя метода в классе для вызова
    method_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Флаг устаревания
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False)
    deprecation_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # SHA256 от canonical JSON {input_schema, output_schema} — для observability и валидации
    schema_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # ID билда воркера (git sha / build id) — для трекинга какой код в проде
    worker_build_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Когда последний раз видели при sync — для детекта "мёртвых" версий
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Дата синхронизации из кода в БД
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        nullable=False
    )
    
    # Relationships
    tool: Mapped["Tool"] = relationship(
        "Tool", 
        back_populates="backend_releases",
        foreign_keys=[tool_id]
    )
    
    # Releases that use this backend version
    releases: Mapped[list["ToolRelease"]] = relationship(
        "ToolRelease",
        back_populates="backend_release",
        foreign_keys="ToolRelease.backend_release_id"
    )

    def __repr__(self) -> str:
        return f"<ToolBackendRelease {self.tool_id}@{self.version}>"


class ToolRelease(Base):
    """
    Версия инструмента для использования агентами.

    Жизненный цикл:
    - draft: можно редактировать
    - active: используется агентами, нельзя редактировать
    - archived: только для истории
    """
    __tablename__ = "tool_releases"

    __table_args__ = (
        UniqueConstraint('tool_id', 'version', name='uq_tool_release_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    backend_release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_backend_releases.id", ondelete="RESTRICT"),
        nullable=True,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=ToolReleaseStatus.DRAFT.value,
        nullable=False,
        index=True
    )

    # ── Meta ────────────────────────────────────────────────────────────
    meta_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expected_schema_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    parent_release_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_releases.id", ondelete="SET NULL"),
        nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    tool: Mapped["Tool"] = relationship(
        "Tool",
        back_populates="releases",
        foreign_keys=[tool_id]
    )

    backend_release: Mapped["ToolBackendRelease"] = relationship(
        "ToolBackendRelease",
        back_populates="releases",
        foreign_keys=[backend_release_id]
    )

    parent_release: Mapped[Optional["ToolRelease"]] = relationship(
        "ToolRelease",
        remote_side="ToolRelease.id",
        foreign_keys=[parent_release_id],
    )

    @property
    def is_editable(self) -> bool:
        return self.status == ToolReleaseStatus.DRAFT.value

    @property
    def can_activate(self) -> bool:
        return self.status == ToolReleaseStatus.DRAFT.value

    def __repr__(self) -> str:
        return f"<ToolRelease {self.tool_id}@v{self.version} ({self.status})>"
