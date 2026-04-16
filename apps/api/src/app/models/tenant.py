
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from .base import Base

class Tenants(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Model-related fields
    embedding_model_alias: Mapped[str | None] = mapped_column(String(100), ForeignKey("models.alias"), nullable=True)
    chunk_profile: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Default chunking profile (by_tokens, by_paragraphs, etc.)")
    chunk_size: Mapped[int | None] = mapped_column(nullable=True, comment="Default chunk size in tokens")
    chunk_overlap: Mapped[int | None] = mapped_column(nullable=True, comment="Default chunk overlap in tokens")
    ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    layout: Mapped[bool] = mapped_column(Boolean, default=False)
    default_agent_slug: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Default agent slug for this tenant")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class UserTenants(Base):
    __tablename__ = "user_tenants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
