"""
OrchestrationSettings model — singleton table for global orchestration configuration.

Stores executor settings used by AgentRuntime.
Only one row should exist (enforced by application logic + seed).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Float
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
    executor_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Default model alias for execution/generation")
    executor_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.7)
    executor_timeout_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Default timeout for executor in seconds")
    executor_max_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Default max planner loop iterations")

    # Legacy DB columns may still exist physically (historical migrations),
    # but they are intentionally not mapped/used by runtime anymore.

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
