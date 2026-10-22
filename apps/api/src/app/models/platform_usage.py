"""Compact usage records, independent of diagnostic journals and source retention."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformUsage(Base):
    __tablename__ = "platform_usage"
    __table_args__ = (Index("ix_platform_usage_period", "kind", "origin", "started_at"),)

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    origin: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    agent_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="running")
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    token_source: Mapped[str | None] = mapped_column(String(16), nullable=True)


class PlatformUsageCoverage(Base):
    __tablename__ = "platform_usage_coverage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
