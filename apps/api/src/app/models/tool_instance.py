"""
ToolInstance model - конкретное подключение к инструменту
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, func, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InstanceScope(str, Enum):
    """Scope уровень для ToolInstance"""
    DEFAULT = "default"
    TENANT = "tenant"
    USER = "user"


class HealthStatus(str, Enum):
    """Статус здоровья ToolInstance"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ToolInstance(Base):
    """
    Конкретный instance инструмента с настройками подключения.
    
    Примеры:
    - "jira-prod" - Jira Production
    - "jira-staging" - Jira Staging  
    - "netbox-main" - NetBox основной
    
    Scope определяет уровень доступности:
    - default: глобальный, доступен всем
    - tenant: доступен конкретному тенанту
    - user: доступен конкретному пользователю
    """
    __tablename__ = "tool_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    
    connection_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    health_status: Mapped[str] = mapped_column(String(20), default=HealthStatus.UNKNOWN.value)
    last_health_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    health_check_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('default', 'tenant', 'user')",
            name="tool_instances_scope_check"
        ),
        CheckConstraint(
            """
            (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
            (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
            """,
            name="tool_instances_scope_refs_check"
        ),
    )

    def __repr__(self) -> str:
        return f"<ToolInstance {self.slug} ({self.scope})>"
