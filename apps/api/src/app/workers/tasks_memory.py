"""
Memory writeback tasks — off-load memory finalization to Celery.

This module provides background task for persisting turn memory effects
(facts + summary) without blocking the SSE stream.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.memory import FactScope
from app.runtime.memory.dto import SummaryDTO, FactDTO
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.writer import MemoryWriter

logger = get_logger(__name__)


class FactPayload(BaseModel):
    """Serializable fact for Celery transport."""
    scope: str
    subject: str
    value: str
    source: str = "USER_UTTERANCE"
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    chat_id: Optional[str] = None
    confidence: float = 1.0


class SummaryPayload(BaseModel):
    """Serializable summary for Celery transport."""
    chat_id: str
    goals: List[str] = Field(default_factory=list)
    done: List[str] = Field(default_factory=list)
    entities: Dict[str, str] = Field(default_factory=dict)
    open_questions: List[str] = Field(default_factory=list)
    raw_tail: str = ""
    last_updated_turn: int = 0


class AgentResultPayload(BaseModel):
    """Serializable agent result snippet."""
    agent: str
    summary: str = ""
    success: bool = True


class MemoryFinalizePayload(BaseModel):
    """
    Serializable payload for memory finalization task.
    
    All UUIDs are serialized as strings for JSON compatibility.
    """
    chat_id: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    turn_number: int
    user_message: str
    assistant_final: str
    
    # Memory bundle data
    summary: SummaryPayload
    retrieved_facts: List[FactPayload] = Field(default_factory=list)
    agent_results: List[AgentResultPayload] = Field(default_factory=list)
    
    # Control flags
    skip_llm_helpers: bool = False
    terminal_reason: Optional[str] = None
    sandbox_overrides: Optional[Dict[str, Any]] = None


def get_async_session():
    """Create async session for Celery tasks."""
    db_url = os.getenv("ASYNC_DB_URL") or os.getenv("DATABASE_URL", "").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(db_url, echo=False)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _deserialize_turn_memory(payload: MemoryFinalizePayload) -> TurnMemory:
    """Reconstruct TurnMemory from serializable payload."""
    # Reconstruct facts
    facts = [
        FactDTO(
            scope=FactScope(f.scope),
            subject=f.subject,
            value=f.value,
            source=f.source,
            user_id=UUID(f.user_id) if f.user_id else None,
            tenant_id=UUID(f.tenant_id) if f.tenant_id else None,
            chat_id=UUID(f.chat_id) if f.chat_id else None,
            confidence=f.confidence,
        )
        for f in payload.retrieved_facts
    ]
    
    # Reconstruct summary
    summary = SummaryDTO(
        chat_id=UUID(payload.summary.chat_id),
        goals=payload.summary.goals,
        done=payload.summary.done,
        entities=payload.summary.entities,
        open_questions=payload.summary.open_questions,
        raw_tail=payload.summary.raw_tail,
        last_updated_turn=payload.summary.last_updated_turn,
    )
    
    # Build minimal TurnMemory
    memory = TurnMemory(
        chat_id=UUID(payload.chat_id),
        user_id=UUID(payload.user_id) if payload.user_id else None,
        tenant_id=UUID(payload.tenant_id) if payload.tenant_id else None,
        turn_number=payload.turn_number,
        goal="",  # Not needed for writeback
        summary=summary,
        retrieved_facts=facts,
    )
    
    # Attach agent results
    memory.agent_results = [
        {"agent": r.agent, "summary": r.summary, "success": r.success}
        for r in payload.agent_results
    ]
    
    return memory


@shared_task(
    name="app.workers.tasks_memory.finalize_memory",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="memory",
)
def finalize_memory_task(self, payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Background task to finalize memory writeback.
    
    This runs FactExtractor + SummaryCompactor in parallel and persists
    the results without blocking the main SSE stream.
    
    Args:
        payload_dict: Serialized MemoryFinalizePayload
        
    Returns:
        Dict with status and component results
    """
    import asyncio
    
    async def _finalize():
        payload = MemoryFinalizePayload.model_validate(payload_dict)
        AsyncSessionLocal = get_async_session()
        
        async with AsyncSessionLocal() as session:
            # Create LLM client from settings
            from app.core.di import get_llm_client

            llm_client = get_llm_client()
            
            # Reconstruct TurnMemory
            turn_memory = _deserialize_turn_memory(payload)
            
            # Run memory writer
            writer = MemoryWriter(
                session=session,
                llm_client=llm_client,
            )
            
            from app.runtime.contracts import PipelineStopReason
            
            terminal_reason = None
            if payload.terminal_reason:
                try:
                    terminal_reason = PipelineStopReason(payload.terminal_reason)
                except ValueError:
                    logger.warning("Unknown terminal reason: %s", payload.terminal_reason)
            
            await writer.finalize(
                memory=turn_memory,
                user_message=payload.user_message,
                assistant_final=payload.assistant_final,
                terminal_reason=terminal_reason,
                sandbox_overrides=payload.sandbox_overrides,
            )
            
            diagnostics = turn_memory.memory_diagnostics or {}
            write_status = diagnostics.get("memory_write_status", {})
            
            return {
                "status": "ok",
                "chat_id": payload.chat_id,
                "turn_number": payload.turn_number,
                "components": write_status.get("results", []),
                "failed": write_status.get("failed_components", []),
                "degraded": write_status.get("degraded_components", []),
            }
    
    try:
        return asyncio.run(_finalize())
    except Exception as exc:
        logger.exception("Memory finalization failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(
    name="app.workers.tasks_memory.finalize_memory_inline",
    bind=True,
    max_retries=0,
)
def finalize_memory_inline_task(self, payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inline fallback for memory finalization (used when Celery is disabled).
    
    Same logic as finalize_memory but without queue routing.
    """
    return finalize_memory_task.run(self, payload_dict)
