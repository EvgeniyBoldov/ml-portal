"""
Policy model - execution limits and constraints for agents
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import String, Boolean, DateTime, Text, Integer, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Policy(Base):
    """
    Execution policy with limits, timeouts, and budgets.
    
    Agents reference a policy to control their execution behavior.
    Numeric fields are explicit for common limits, extra_config for extensions.
    """
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Execution limits
    max_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_tool_calls: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_wall_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Tool execution
    tool_timeout_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_retries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Budget limits
    budget_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    budget_cost_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Extended configuration (for future fields before they become explicit)
    extra_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Policy {self.slug}>"
