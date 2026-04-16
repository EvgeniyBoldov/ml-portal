"""
RoutingLog model - логирование решений Router
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import String, DateTime, Text, Integer, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RoutingLog(Base):
    """
    Лог routing/preflight решений.
    
    Сохраняет информацию о:
    - Классификации intent
    - Выборе агента
    - Проверке prerequisites
    - Режиме выполнения
    
    Используется для анализа и отладки routing decisions.
    """
    __tablename__ = "routing_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    request_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    intent_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    selected_agent_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    agent_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    routing_reasons: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    missing_tools: Mapped[List[str]] = mapped_column(JSONB, default=list)
    missing_collections: Mapped[List[str]] = mapped_column(JSONB, default=list)
    missing_credentials: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    execution_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    effective_operations: Mapped[List[str]] = mapped_column(JSONB, default=list)
    effective_data_instances: Mapped[List[str]] = mapped_column(JSONB, default=list)
    operation_targets: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    routed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    routing_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<RoutingLog {self.run_id} agent={self.selected_agent_slug}>"
