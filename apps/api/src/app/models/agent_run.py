import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgentRun(Base):
    """
    Represents a single execution of an agent.
    Tracks the overall run status, metrics, and links to individual steps.
    """
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    chat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('chats.id', ondelete='CASCADE'), nullable=True
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('chatmessages.id', ondelete='CASCADE'), nullable=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False
    )
    
    agent_slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # none, brief, full — copied from Agent at run start
    logging_level: Mapped[str] = mapped_column(String(10), nullable=False, default='brief', server_default='brief')
    
    # running, completed, failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default='running')
    
    # Snapshot of versions/config at run start (frozen for reproducibility)
    # Keys: agent_version, prompt_hash, policy_version, limit_version,
    #        tools, collections, permissions, model, routing
    context_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Aggregated metrics
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Pause state for run continuation (waiting_confirmation / waiting_input)
    paused_action: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    paused_context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    steps: Mapped[List["AgentRunStep"]] = relationship(
        "AgentRunStep", back_populates="run", cascade="all, delete-orphan",
        order_by="AgentRunStep.step_number"
    )

    def __repr__(self):
        return f"<AgentRun {self.id} agent={self.agent_slug} status={self.status}>"


class AgentRunStep(Base):
    """
    Individual step within an agent run.
    
    Step types:
    - user_request:   {content, model, agent_slug}
    - routing:        {mode, available_tools, permissions, policy, limits, duration_ms}
    - llm_request:    {step, model, messages_count, messages (full only), system_prompt_hash}
    - llm_response:   {step, content (full only), has_tool_calls, tool_calls_count, finish_reason}
    - tool_call:      {tool_slug, call_id, arguments, schema_hash}
    - tool_result:    {tool_slug, call_id, success, result (full only), error}
    - final_response: {step, content_length, has_sources, sources_count}
    - error:          {error, step, recoverable}
    """
    __tablename__ = "agent_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('agent_runs.id', ondelete='CASCADE'), nullable=False
    )
    
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    step_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    
    # Relationship
    run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="steps")

    def __repr__(self):
        return f"<AgentRunStep {self.step_number} type={self.step_type}>"
