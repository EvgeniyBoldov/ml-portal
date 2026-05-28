"""
OrchestrationSettings model — singleton table for global orchestration configuration.

Stores executor settings used by AgentRuntime.
Only one row should exist (enforced by application logic + seed).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrchestrationSettings(Base):
    """
    Global orchestration settings (singleton).
    
    Stores executor configuration used by AgentRuntime (run_direct + run_with_planner).
    Router/Planner models are configured via SystemLLMRole.
    Caps / safety gates live in PlatformSettings.
    """
    __tablename__ = "orchestration_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # === Executor Settings ===
    executor_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Псевдоним модели по умолчанию для выполнения/генерации")
    executor_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.7)
    tool_use_guard: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True, comment="Текст политики использования инструментов (ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА)")
    retry_instruction: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment="Инструкция для повтора при отсутствии вызова операции")
    intent_messages: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="Сообщения намерений (i18n)")
    prompt_budgets: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="Бюджеты промптов (magic numbers)")
    prompt_labels: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="Лейблы промптов (i18n)")
    # Legacy DB columns may still exist physically until cleanup migration.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def __repr__(self):
        return f"<OrchestrationSettings {self.id}>"
