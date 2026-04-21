"""
SystemLLMRole model — structured LLM roles for triage, planner, and summary.

Stores prompt parts and execution configuration for system-level LLM roles.
Each role type has strict contracts and structured input.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy import String, DateTime, Text, Boolean, Integer, Float, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Import for relationship - will be resolved after both models are loaded
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.system_llm_trace import SystemLLMTrace


class SystemLLMRoleType(str, Enum):
    """System LLM role types."""
    TRIAGE = "triage"
    PLANNER = "planner"
    SUMMARY = "summary"
    MEMORY = "memory"
    SYNTHESIZER = "synthesizer"
    FACT_EXTRACTOR = "fact_extractor"
    SUMMARY_COMPACTOR = "summary_compactor"


class RetryBackoffType(str, Enum):
    """Retry backoff strategies."""
    NONE = "none"
    LINEAR = "linear"
    EXP = "exp"


class SystemLLMRole(Base):
    """
    System LLM role configuration.
    
    Stores structured prompt parts and execution settings for triage, planner, and summary roles.
    """
    __tablename__ = "system_llm_roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # === Role Identification ===
    role_type: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("role_type IN ('triage', 'planner', 'summary', 'memory', 'synthesizer', 'fact_extractor', 'summary_compactor')", name="check_system_llm_role_type"),
        nullable=False,
        comment="Role type: triage | planner | summary | memory"
    )
    
    # === Prompt Parts ===
    identity: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Role identity description"
    )
    
    mission: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Role mission and purpose"
    )
    
    rules: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Core rules and guidelines"
    )
    
    safety: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Safety constraints and rules"
    )
    
    output_requirements: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Output format and structure requirements"
    )
    
    # === Few-shot Examples ===
    examples: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Few-shot examples for the role"
    )
    
    # === Execution Configuration ===
    model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Model alias for this role"
    )
    
    temperature: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Temperature for LLM calls"
    )
    
    max_tokens: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Maximum tokens for LLM response"
    )
    
    timeout_s: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Timeout in seconds"
    )
    
    max_retries: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Maximum retry attempts"
    )
    
    retry_backoff: Mapped[Optional[str]] = mapped_column(
        String(10),
        CheckConstraint("retry_backoff IN ('none', 'linear', 'exp')", name="check_retry_backoff_type"),
        nullable=True,
        comment="Retry backoff strategy: none | linear | exp"
    )
    
    # === Status ===
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, default=True,
        comment="Whether this role configuration is active"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    traces: Mapped[List["SystemLLMTrace"]] = relationship(
        "app.models.system_llm_trace.SystemLLMTrace",
        back_populates="role"
    )

    def __repr__(self):
        return f"<SystemLLMRole {self.role_type.value} active={self.is_active}>"

    @property
    def compiled_prompt(self) -> str:
        """Compile prompt parts into a single system prompt."""
        parts = []
        
        if self.identity:
            parts.append(f"# IDENTITY\n{self.identity}")
        
        if self.mission:
            parts.append(f"# MISSION\n{self.mission}")
            
        if self.rules:
            parts.append(f"# RULES\n{self.rules}")
            
        if self.safety:
            parts.append(f"# SAFETY\n{self.safety}")
            
        if self.output_requirements:
            parts.append(f"# OUTPUT REQUIREMENTS\n{self.output_requirements}")
        
        # Add examples if present
        if self.examples:
            parts.append(f"# EXAMPLES")
            for i, example in enumerate(self.examples, 1):
                parts.append(f"## Example {i}")
                if example.get("description"):
                    parts.append(f"Description: {example['description']}")
                if example.get("input"):
                    parts.append(f"Input: {example['input']}")
                if example.get("output"):
                    parts.append(f"Output: {example['output']}")
                parts.append("")  # Empty line between examples
        
        return "\n\n".join(parts) if parts else "You are a helpful assistant."
