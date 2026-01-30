"""
AgentBinding model - связь агента с инструментом и инстансом
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CredentialStrategy(str, Enum):
    """
    Стратегия выбора кредов для инструмента.
    
    USER_ONLY - только креды пользователя
    TENANT_ONLY - только креды тенанта
    DEFAULT_ONLY - только дефолтные креды
    PREFER_USER - сначала юзер, потом тенант, потом default
    PREFER_TENANT - сначала тенант, потом юзер, потом default
    ANY - любые доступные (user → tenant → default)
    """
    USER_ONLY = "user_only"
    TENANT_ONLY = "tenant_only"
    DEFAULT_ONLY = "default_only"
    PREFER_USER = "prefer_user"
    PREFER_TENANT = "prefer_tenant"
    ANY = "any"


class AgentBinding(Base):
    """
    Связь агента с конкретным инструментом и инстансом.
    
    Определяет:
    - Какой инструмент (Tool) использует агент
    - Какой инстанс (ToolInstance) использовать
    - Какую стратегию выбора кредов применять
    - Обязателен ли инструмент для работы агента
    
    Примеры:
    - Agent "jira-assistant" + Tool "jira.create" + Instance "jira-prod" + USER_ONLY
    - Agent "rag-chat" + Tool "rag.search" + Instance "rag-local" + ANY
    """
    __tablename__ = "agent_bindings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # FK to Agent
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("agents.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # FK to Tool (конкретная операция: jira.create, rag.search)
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("tools.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # FK to ToolInstance (конкретный инстанс: jira-prod, rag-local)
    tool_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("tool_instances.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Стратегия выбора кредов
    credential_strategy: Mapped[str] = mapped_column(
        String(20), 
        default=CredentialStrategy.ANY.value, 
        nullable=False
    )
    
    # Обязателен ли инструмент для работы агента
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    __table_args__ = (
        # Уникальность: один агент не может иметь два биндинга на один и тот же tool
        UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )

    def __repr__(self):
        return f"<AgentBinding agent={self.agent_id} tool={self.tool_id} instance={self.tool_instance_id}>"
