import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Agent(Base):
    """
    Agent configuration entity.
    Combines a System Prompt, Policy, Limit, and Tool Bindings.
    Acts as a profile for the Chat/LLM interaction.
    
    Tool bindings are stored in AgentBinding table (agent_id → tool_id → instance_id).
    Policy controls execution limits and behavior.
    Capabilities are used by Router for agent selection.
    """
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Reference to system prompt (by slug)
    system_prompt_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Reference to Policy entity with behavioral rules/restrictions
    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('policies.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Reference to Limit entity with execution limits
    limit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('limits.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # Capabilities for Router matching
    # ["knowledge_base_search", "ticket_management", "code_generation"]
    capabilities: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    # Whether agent can run in partial mode (some tools unavailable)
    supports_partial_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # LLM generation config (temperature, max_tokens, etc.)
    generation_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    enable_logging: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc), 
        nullable=False
    )

    def __repr__(self):
        return f"<Agent {self.slug}>"
