"""
Memory writeback tasks — off-load memory finalization to Celery.

This module provides background task for persisting turn memory effects
(facts + summary) without blocking the SSE stream.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional
from uuid import UUID
from uuid import uuid4

from celery import shared_task
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.logging import get_logger
from app.models.memory import FactScope
from app.runtime.memory.dto import SummaryDTO, FactDTO
from app.runtime.memory.fact_extractor import AgentResultSnippet
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.writer import MemoryWriter
from app.runtime.events import RuntimeEvent
from app.services.runtime_tail_event_bus import RuntimeTailEventBus

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
    chat_id: Optional[str] = None
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
    runtime_run_id: Optional[str] = None
    tail_id: Optional[str] = None
    stream_key: Optional[str] = None


def get_async_session():
    """Create async session for Celery tasks."""
    db_url = os.getenv("ASYNC_DB_URL") or os.getenv("DATABASE_URL", "").replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    engine = create_async_engine(db_url, echo=False)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _deserialize_turn_memory(payload: MemoryFinalizePayload) -> TurnMemory:
    """Reconstruct TurnMemory from serializable payload."""
    fallback_chat_id = payload.summary.chat_id if payload.summary and payload.summary.chat_id else None
    chat_id_str = payload.chat_id or fallback_chat_id
    if not chat_id_str:
        raise ValueError("MemoryFinalizePayload.chat_id is required")
    parsed_chat_id = UUID(chat_id_str)

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
        chat_id=parsed_chat_id,
        goals=payload.summary.goals,
        done=payload.summary.done,
        entities=payload.summary.entities,
        open_questions=payload.summary.open_questions,
        raw_tail=payload.summary.raw_tail,
        last_updated_turn=payload.summary.last_updated_turn,
    )
    
    # Build minimal TurnMemory
    memory = TurnMemory(
        chat_id=parsed_chat_id,
        user_id=UUID(payload.user_id) if payload.user_id else None,
        tenant_id=UUID(payload.tenant_id) if payload.tenant_id else None,
        turn_number=payload.turn_number,
        goal="",  # Not needed for writeback
        summary=summary,
        retrieved_facts=facts,
    )
    
    # Attach agent results
    memory.agent_results = [
        AgentResultSnippet(agent=r.agent, summary=r.summary, success=r.success)
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
        bus = RuntimeTailEventBus()

        async def _publish(event: RuntimeEvent) -> None:
            if not payload.stream_key:
                return
            message = {
                "type": event.type.value,
                "run_id": payload.stream_key,
                **dict(event.data or {}),
            }
            if payload.tail_id:
                message["tail_id"] = payload.tail_id
            await bus.publish(stream_key=payload.stream_key, payload=message)

        async with AsyncSessionLocal() as session:
            # Create LLM client from settings
            from app.core.di import get_llm_client

            llm_client = get_llm_client()
            
            # Reconstruct TurnMemory
            turn_memory = _deserialize_turn_memory(payload)
            
            # Run memory writer
            component_entity_ids = {
                "facts": f"{payload.runtime_run_id or payload.chat_id}:memory:facts",
                "conversation": f"{payload.runtime_run_id or payload.chat_id}:memory:conversation",
            }

            async def _on_llm_event(component_name: str, llm_payload: dict[str, Any]) -> None:
                parent_id = component_entity_ids.get(component_name, memory_orchestrator_id)
                messages = llm_payload.get("messages")
                response_text = llm_payload.get("response")
                await _publish(
                    RuntimeEvent.llm_turn(
                        llm_call_id=f"{parent_id}:llm:{uuid4().hex[:8]}",
                        parent_entity_type="agent_run",
                        parent_entity_id=parent_id,
                        purpose=str(llm_payload.get("role") or component_name),
                        model=llm_payload.get("model"),
                        temperature=(llm_payload.get("params") or {}).get("temperature"),
                        max_tokens=(llm_payload.get("params") or {}).get("max_tokens"),
                        messages=messages if isinstance(messages, list) else None,
                        content=str(response_text) if isinstance(response_text, str) else None,
                        response=str(response_text) if isinstance(response_text, str) else None,
                        duration_ms=llm_payload.get("duration_ms"),
                    )
                )

            writer = MemoryWriter(
                session=session,
                llm_client=llm_client,
                llm_event_callback=_on_llm_event,
            )
            
            from app.runtime.contracts import PipelineStopReason
            
            terminal_reason = None
            if payload.terminal_reason:
                try:
                    terminal_reason = PipelineStopReason(payload.terminal_reason)
                except ValueError:
                    logger.warning("Unknown terminal reason: %s", payload.terminal_reason)
            
            memory_orchestrator_id = (
                f"{payload.runtime_run_id}:memory"
                if payload.runtime_run_id
                else f"{payload.chat_id}:memory"
            )
            memory_status = "completed"
            results: list[dict[str, Any]] = []
            failed_components: list[str] = []
            degraded_components: list[str] = []
            await _publish(
                RuntimeEvent.orchestrator_start(
                    orchestrator_id=memory_orchestrator_id,
                    run_id=payload.runtime_run_id or payload.chat_id,
                    role="memory",
                )
            )
            try:
                for component_name, component_entity_id in component_entity_ids.items():
                    await _publish(
                        RuntimeEvent.agent_start(
                            agent_run_id=component_entity_id,
                            parent_entity_id=memory_orchestrator_id,
                            parent_entity_type="orchestrator",
                            agent_slug=component_name,
                        )
                    )
                await writer.finalize(
                    memory=turn_memory,
                    user_message=payload.user_message,
                    assistant_final=payload.assistant_final,
                    terminal_reason=terminal_reason,
                    sandbox_overrides=payload.sandbox_overrides,
                )
                diagnostics = turn_memory.memory_diagnostics or {}
                write_status = diagnostics.get("memory_write_status", {})
                results = [
                    item for item in (write_status.get("results") or [])
                    if isinstance(item, dict)
                ]
                failed_components = [
                    str(name) for name in (write_status.get("failed_components") or [])
                ]
                degraded_components = [
                    str(name) for name in (write_status.get("degraded_components") or [])
                ]

                for index, item in enumerate(results, start=1):
                    component_name = str(item.get("component_name") or "unknown")
                    component_entity_id = component_entity_ids.get(
                        component_name,
                        f"{payload.runtime_run_id or payload.chat_id}:memory:{component_name}:{index}",
                    )
                    component_status = str(item.get("status") or "completed")
                    lifecycle_status = "failed" if component_status == "failed" else (
                        "paused" if component_status in {"degraded", "skipped"} else "completed"
                    )
                    await _publish(
                        RuntimeEvent.status(
                            "memory_component_result",
                            component_name=component_name,
                            status=component_status,
                            inserted_count=item.get("inserted_count", 0),
                            updated_count=item.get("updated_count", 0),
                            skipped_count=item.get("skipped_count", 0),
                            error_code=item.get("error_code"),
                            error_message=item.get("error_message"),
                            duration_ms=item.get("duration_ms", 0),
                            parent_entity_type="agent_run",
                            parent_entity_id=component_entity_id,
                        )
                    )
                    await _publish(
                        RuntimeEvent.agent_end(
                            agent_run_id=component_entity_id,
                            parent_entity_id=memory_orchestrator_id,
                            parent_entity_type="orchestrator",
                            agent_slug=component_name,
                            status=lifecycle_status,
                        )
                    )
            except Exception:
                memory_status = "failed"
                raise
            finally:
                await _publish(
                    RuntimeEvent.status(
                        "memory_write_end",
                        turn_number=payload.turn_number,
                        failed_components=failed_components,
                        degraded_components=degraded_components,
                        parent_entity_type="orchestrator",
                        parent_entity_id=memory_orchestrator_id,
                    )
                )
                await _publish(
                    RuntimeEvent.orchestrator_end(
                        orchestrator_id=memory_orchestrator_id,
                        run_id=payload.runtime_run_id or payload.chat_id,
                        status=memory_status,
                    )
                )
                await _publish(
                    RuntimeEvent.status(
                        "tail_finished",
                        tail_id=payload.tail_id,
                        status=memory_status,
                        parent_entity_type="orchestrator",
                        parent_entity_id=memory_orchestrator_id,
                    )
                )

            return {
                "status": "ok",
                "chat_id": payload.chat_id,
                "turn_number": payload.turn_number,
                "components": results,
                "failed": failed_components,
                "degraded": degraded_components,
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
