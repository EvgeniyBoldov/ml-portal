"""
PlatformSettings model — singleton table for global platform configuration.

Stores global policy text, safety gates, and platform caps.
Only one row should exist (enforced by application logic + seed).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformSettings(Base):
    """
    Global platform settings (singleton).
    
    Stores global policy text, safety gates, and absolute platform caps.
    These settings apply to all tenants/users as the maximum allowed values.
    """
    __tablename__ = "platform_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # === Global Policy Settings ===
    
    # Policy text for planner/executor (markdown)
    policies_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Policy gates - global safety flags
    require_confirmation_for_write: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    require_confirmation_for_destructive: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    forbid_destructive: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    forbid_write_in_prod: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    require_backup_before_write: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    
    # === Global Caps / Rails ===
    
    # Absolute maximum limits (platform ceilings)
    abs_max_timeout_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abs_max_retries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abs_max_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abs_max_plan_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abs_max_concurrency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abs_max_task_runtime_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    abs_max_tool_calls_per_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # === Chat File Upload ===
    chat_upload_max_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chat_upload_allowed_extensions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        return f"<PlatformSettings {self.id}>"
