"""Admission ledger shared across retries of one machine invocation."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShadowExecutionGuard(Base):
    __tablename__ = "shadow_execution_guards"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    calls: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
