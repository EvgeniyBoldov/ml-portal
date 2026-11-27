from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssignmentIntegration(Base):
    __tablename__ = "assignment_integrations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(97), unique=True)
    connector_id: Mapped[UUID] = mapped_column(ForeignKey("tool_instances.id", ondelete="RESTRICT"), index=True)
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AssignmentIntegrationToken(Base):
    __tablename__ = "assignment_integration_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    integration_id: Mapped[UUID] = mapped_column(
        ForeignKey("assignment_integrations.id", ondelete="CASCADE"), index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    token_hash: Mapped[str] = mapped_column(Text)
    token_prefix: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(server_default="true")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
