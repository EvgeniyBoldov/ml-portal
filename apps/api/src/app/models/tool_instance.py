"""
ToolInstance model - конкретное подключение к системе
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HealthStatus(str, Enum):
    """Статус здоровья ToolInstance"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class InstanceType(str, Enum):
    """Тип инстанса"""
    LOCAL = "local"      # Локальный (коллекции, внутренние сервисы)
    HTTP = "http"        # Внешний HTTP API
    CUSTOM = "custom"    # Кастомный тип


class ToolInstance(Base):
    """
    Конкретный instance системы с настройками подключения.
    
    Примеры:
    - "jira-prod" - Jira Production
    - "jira-staging" - Jira Staging  
    - "netbox-main" - NetBox основной
    - "remedy-1", "remedy-2" - несколько инстансов Remedy
    
    Инстансы глобальные, креды привязываются через CredentialSet.
    """
    __tablename__ = "tool_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # FK to ToolGroup (e.g., "jira", "rag", "netbox")
    tool_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Connection configuration (url, project mappings, etc.)
    connection_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Instance metadata (env=prod/stage/dev, region, etc.)
    instance_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Instance type: local (collections), http (external APIs), custom
    instance_type: Mapped[str] = mapped_column(String(20), default=InstanceType.HTTP.value, nullable=False)
    
    health_status: Mapped[str] = mapped_column(String(20), default=HealthStatus.UNKNOWN.value)
    last_health_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    health_check_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ToolInstance {self.slug}>"
