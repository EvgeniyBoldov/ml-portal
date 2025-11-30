import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Boolean, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Prompt(Base):
    """
    Prompt template registry for LLM interactions.
    Supports versioning and Jinja2 templating.
    """
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Human-readable unique identifier (e.g., "chat.rag.system", "agent.netbox.config_gen")
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    
    # Display name for UI
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description for internal usage (MLOps documentation)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # The prompt template content (Jinja2 format)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Expected input variables for validation (e.g., ["query", "context"])
    input_variables: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    # Model configuration override (e.g., {"temperature": 0.2, "model": "gpt-4"})
    model_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Classification
    type: Mapped[str] = mapped_column(String(50), default="chat", nullable=False)  # chat, agent, task
    
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
        return f"<Prompt {self.slug} (v{self.version})>"
