from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class LifecycleMixin:
    """Unified soft-delete lifecycle fields for owner entities."""

    lifecycle_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deprecated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deprecated_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=14, server_default="14"
    )

    @property
    def is_deprecated(self) -> bool:
        return self.lifecycle_status == "deprecated"
