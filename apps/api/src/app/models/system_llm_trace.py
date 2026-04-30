"""
SystemLLMTrace model for logging triage, planner, and summary LLM calls.

Captures complete trace of system LLM execution including prompt assembly,
input data, raw/parsed responses, and validation status.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# Import for relationship - will be resolved after both models are loaded
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.system_llm_role import SystemLLMRole


class SystemLLMTraceType(str, Enum):
    """Types of system LLM traces."""
    PLANNER = "planner"
    SUMMARY = "summary"


class SystemLLMTrace(Base):
    """
    Complete trace of a system LLM execution (triage/planner/summary).
    
    Stores prompt assembly, input data, LLM call details, and response validation.
    """
    __tablename__ = "system_llm_traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # === Classification ===
    trace_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="triage | planner | summary"
    )
    
    # === Relationships ===
    chat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('chats.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
        comment="Associated chat session (optional)"
    )
    
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('agent_runs.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
        comment="Associated agent run (optional)"
    )
    
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
        comment="Tenant ID for multi-tenancy"
    )
    
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment="User who initiated the trace"
    )
    
    # === Prompt Assembly ===
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('system_llm_roles.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment="SystemLLMRole used for this trace"
    )
    
    role_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Frozen snapshot of role configuration at execution time"
    )
    
    compiled_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Final assembled prompt sent to LLM"
    )
    
    compiled_prompt_hash: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        comment="SHA-256 hash of compiled prompt for deduplication"
    )
    
    # === Input Data ===
    structured_input: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Complete input (TriageInput/PlannerInput/SummaryInput)"
    )
    
    context_variables: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Additional context variables (available_agents, tools, etc.)"
    )
    
    # === LLM Call ===
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="LLM model used"
    )
    
    temperature: Mapped[float] = mapped_column(
        nullable=False,
        comment="Temperature setting"
    )
    
    max_tokens: Mapped[int] = mapped_column(
        nullable=False,
        comment="Max tokens setting"
    )
    
    messages_sent: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Complete messages array sent to LLM"
    )
    
    # === Response ===
    raw_response: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Raw LLM response before parsing"
    )
    
    parsed_response: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Parsed response after JSON extraction"
    )
    
    validation_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="success | failed | fallback_applied"
    )
    
    validation_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Validation error if any"
    )
    
    fallback_applied: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether smart fallback mapping was applied"
    )
    
    fallback_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Details of fallback mapping if applied"
    )
    
    # === Metrics ===
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Attempt number (1, 2, 3...)"
    )
    
    total_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Total attempts made"
    )
    
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Duration of LLM call in milliseconds"
    )
    
    tokens_in: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Input tokens if available"
    )
    
    tokens_out: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Output tokens if available"
    )
    
    # === Result ===
    result_type: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Result type (final|agent|plan|ask_user for triage, etc.)"
    )
    
    result_summary: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="Brief description of the result"
    )
    
    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
        comment="Trace creation timestamp"
    )
    
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error if trace failed"
    )
    
    # Relationships
    role: Mapped["SystemLLMRole"] = relationship(
        "app.models.system_llm_role.SystemLLMRole",
        back_populates="traces"
    )
    
    def __repr__(self) -> str:
        return f"<SystemLLMTrace {self.id} type={self.trace_type} status={self.validation_status}>"
    
    @property
    def is_success(self) -> bool:
        """Check if trace was successful."""
        return self.validation_status == "success"
    
    @property
    def has_fallback(self) -> bool:
        """Check if fallback was applied."""
        return self.fallback_applied
    
    @property
    def examples_count(self) -> int:
        """Get count of examples in role snapshot."""
        examples = self.role_snapshot.get("examples", [])
        return len(examples) if isinstance(examples, list) else 0
