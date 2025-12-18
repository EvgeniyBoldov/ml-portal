import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

class Agent(Base):
    """
    Agent configuration entity.
    Combines a System Prompt, a set of Tools, and Model configuration.
    Acts as a profile for the Chat/LLM interaction.
    """
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Unique identifier (e.g., "netbox-helper", "general-chat")
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Reference to the System Prompt (by slug)
    # We use slug to be environment-agnostic
    system_prompt_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # List of Tool slugs enabled for this agent
    # e.g. ["netbox.get_device", "rag.search"]
    tools: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    # LLM Model configuration override (optional)
    # e.g. {"model": "gpt-4", "temperature": 0.7}
    # If empty, uses system defaults
    generation_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Enable detailed logging of agent runs for observability
    enable_logging: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )

    def __repr__(self):
        return f"<Agent {self.slug}>"
