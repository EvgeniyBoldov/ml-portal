import uuid
from datetime import datetime, timezone
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
    
    Tools and Collections configuration format:
    tools_config: [
        {"tool_slug": "rag.search", "required": true, "recommended": false},
        {"tool_slug": "jira.create", "required": false, "recommended": true}
    ]
    collections_config: [
        {"collection_slug": "tickets", "required": false, "recommended": true}
    ]
    
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
    
    system_prompt_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Optional baseline prompt for restrictions/limitations
    # Must reference a prompt with type='baseline'
    baseline_prompt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('prompts.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # Legacy fields - kept for backward compatibility, will be migrated to *_config
    tools: Mapped[List[str]] = mapped_column(JSONB, default=list)
    available_collections: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    # New structured configuration for tools
    # [{"tool_slug": "rag.search", "required": true, "recommended": false}]
    tools_config: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    
    # New structured configuration for collections
    # [{"collection_slug": "tickets", "required": false, "recommended": true}]
    collections_config: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    
    # Execution policy
    # {
    #   "execution": {"max_steps": 20, "max_tool_calls_total": 50, ...},
    #   "retry": {"max_retries": 3, ...},
    #   "output": {"citations_required": true, ...},
    #   "tool_execution": {"allow_parallel_tool_calls": true, ...}
    # }
    policy: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Capabilities for Router matching
    # ["knowledge_base_search", "ticket_management", "code_generation"]
    capabilities: Mapped[List[str]] = mapped_column(JSONB, default=list)
    
    # Whether agent can run in partial mode (some tools unavailable)
    supports_partial_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    
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

    def get_required_tools(self) -> List[str]:
        """Get list of required tool slugs"""
        return [
            tc["tool_slug"] 
            for tc in self.tools_config 
            if tc.get("required", False)
        ]
    
    def get_required_collections(self) -> List[str]:
        """Get list of required collection slugs"""
        return [
            cc["collection_slug"] 
            for cc in self.collections_config 
            if cc.get("required", False)
        ]
    
    def get_all_tool_slugs(self) -> List[str]:
        """Get all tool slugs (from both legacy and new config)"""
        from_config = [tc["tool_slug"] for tc in self.tools_config]
        return list(set(self.tools + from_config))
    
    def get_all_collection_slugs(self) -> List[str]:
        """Get all collection slugs (from both legacy and new config)"""
        from_config = [cc["collection_slug"] for cc in self.collections_config]
        return list(set(self.available_collections + from_config))

    def __repr__(self):
        return f"<Agent {self.slug}>"
