"""
Memory writeback tasks — off-load memory finalization to Celery.

This module provides background task for persisting turn memory effects
(facts + summary) without blocking the SSE stream.
"""
from __future__ import annotations

import asyncio
import os
import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.memory import FactScope, FactSource
from app.workers.session_factory import get_worker_session
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.context_snapshot import compact_snapshot, prompt_snapshot
from app.runtime.memory.dto import SummaryDTO, FactDTO
from app.runtime.memory.fact_extractor import AgentResultSnippet, FactEvidence
from app.runtime.memory.transport import TurnMemory
from app.runtime.project_memory_candidates import ProjectMemoryCandidate
from app.runtime.memory.writer import MemoryWriter
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.entity_ids import memory_component_entity_id, memory_orchestrator_id as make_memory_orchestrator_id
from app.services.system_llm_role_service import SystemLLMRoleService
from app.services.runtime_event_logger import RuntimeEventJournalFactory

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


class FactEvidencePayload(BaseModel):
    source_id: str
    source_type: str
    source_ref: str
    text: str
    label: Optional[str] = None


class ProjectMemoryCandidatePayload(BaseModel):
    project_key: str
    subject: str
    value: str
    evidence_call_ids: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)


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
    fact_evidence: List[FactEvidencePayload] = Field(default_factory=list)
    project_memory_candidates: List[ProjectMemoryCandidatePayload] = Field(default_factory=list)
    
    # Control flags
    skip_llm_helpers: bool = False
    terminal_reason: Optional[str] = None
    sandbox_overrides: Optional[Dict[str, Any]] = None
    runtime_run_id: Optional[str] = None
    tail_id: Optional[str] = None
    stream_key: Optional[str] = None
    memory_limits: Optional[Dict[str, int]] = None
    facts_limits: Optional[Dict[str, int]] = None
    conversation_limits: Optional[Dict[str, int]] = None
    logging_level: Optional[str] = None
    runtime_log_context: Optional[Dict[str, Any]] = None


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
            source=FactSource(f.source.lower()),
            tenant_id=UUID(f.tenant_id) if f.tenant_id else None,
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
    memory.fact_evidence = [
        FactEvidence(**item.model_dump()) for item in payload.fact_evidence
    ]
    memory.fact_run_ref = payload.runtime_run_id
    memory.project_memory_candidates = [
        ProjectMemoryCandidate(**item.model_dump())
        for item in payload.project_memory_candidates
    ]
    
    return memory


async def _load_memory_prompts(session: AsyncSession) -> dict[str, str]:
    service = SystemLLMRoleService(session)
    prompts: dict[str, str] = {}
    try:
        facts_cfg = await service.get_role_config(SystemLLMRoleType.FACT_EXTRACTOR)
        prompts["fact_extractor"] = str(facts_cfg.get("prompt") or "")
    except Exception:
        prompts["fact_extractor"] = ""
    try:
        compactor_cfg = await service.get_role_config(SystemLLMRoleType.FACT_COMPACTOR)
        prompts["fact_compactor"] = str(compactor_cfg.get("prompt") or "")
    except Exception:
        prompts["fact_compactor"] = ""
    return prompts


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
    
    This runs FactExtractor followed by FactCompactor and persists the
    results without blocking the main SSE stream.
    
    Args:
        payload_dict: Serialized MemoryFinalizePayload
        
    Returns:
        Dict with status and component results
    """
    import asyncio
    
    async def _finalize():
        payload = MemoryFinalizePayload.model_validate(payload_dict)
        runtime_logger = None
        if payload.runtime_log_context:
            runtime_logger = RuntimeEventJournalFactory.restore_worker(payload.runtime_log_context)
        metric_keys = ("planner_steps", "agent_steps", "tool_calls", "tokens_in", "tokens_out", "tokens_total", "retries", "wall_time_ms")

        async def _publish(event: RuntimeEvent) -> None:
            if runtime_logger is None:
                return
            event_data = dict(event.data or {})
            if payload.tail_id:
                event_data["tail_id"] = payload.tail_id
            from app.runtime.events import OrchestrationPhase
            await runtime_logger.append_runtime_event(
                RuntimeEvent(event.type, event_data), phase=OrchestrationPhase.PIPELINE,
            )

        async with get_worker_session() as session:
            # Create LLM client from settings
            from app.core.di import get_llm_client

            llm_client = get_llm_client()
            
            # Reconstruct TurnMemory
            turn_memory = _deserialize_turn_memory(payload)
            
            # Run memory writer
            component_entity_ids = {
                "fact_extractor": memory_component_entity_id(payload.runtime_run_id or payload.chat_id or "unknown", "fact_extractor", 1),
                "fact_compactor": memory_component_entity_id(payload.runtime_run_id or payload.chat_id or "unknown", "fact_compactor", 2),
            }
            memory_orchestrator_id = make_memory_orchestrator_id(payload.runtime_run_id or payload.chat_id or "unknown")
            component_limits = {"fact_extractor": payload.facts_limits, "fact_compactor": payload.facts_limits}
            budget_own: dict[str, dict[str, int]] = {
                memory_orchestrator_id: {},
                component_entity_ids["fact_extractor"]: {},
                component_entity_ids["fact_compactor"]: {},
            }
            llm_structured_result: dict[str, dict[str, Any]] = {}

            async def _emit_budget_snapshot(
                *,
                entity_type: str,
                entity_id: str,
                parent_entity_id: str,
                role: str,
                limits: Optional[dict[str, int]] = None,
                delta: Optional[dict[str, int]] = None,
                reason: str,
            ) -> None:
                own = budget_own.setdefault(entity_id, {})
                for key, value in (delta or {}).items():
                    own[key] = int(own.get(key, 0)) + int(value)
                await _publish(
                    RuntimeEvent.budget_snapshot(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        parent_entity_type="orchestrator" if entity_type == "agent_execution" else "run",
                        parent_entity_id=parent_entity_id,
                        own=own,
                        limits=limits,
                        delta=delta or {},
                        reason=reason,
                        role=role,
                    )
                )

            llm_token_inputs: dict[str, int] = {}

            async def _on_llm_event(component_name: str, event: RuntimeEvent) -> None:
                event_data = dict(event.data or {})
                llm_call_id = str(event_data.get("llm_call_id") or "")
                if event.type == RuntimeEventType.LLM_REQUEST:
                    messages = event_data.get("messages")
                    request_text = "\n".join(
                        str((message or {}).get("content") or "")
                        for message in (messages or [])
                        if isinstance(message, dict)
                    )
                    llm_token_inputs[llm_call_id] = max(0, len(request_text) // 4)
                    await _publish(event)
                    return

                response_text = event_data.get("response")
                if isinstance(response_text, str) and response_text.strip():
                    try:
                        parsed = json.loads(response_text)
                        if isinstance(parsed, dict):
                            llm_structured_result[component_name] = parsed
                    except Exception:
                        pass
                tokens_in = llm_token_inputs.pop(llm_call_id, 0)
                tokens_out = max(0, len(str(response_text or "")) // 4)
                tokens_total = tokens_in + tokens_out
                event_data.update(
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    tokens_total=tokens_total,
                )
                await _publish(
                    RuntimeEvent(event.type, event_data)
                )
                await _emit_budget_snapshot(
                    entity_type="agent_execution",
                    entity_id=component_entity_ids[component_name],
                    parent_entity_id=memory_orchestrator_id,
                    role=component_name,
                    limits=component_limits.get(component_name),
                    delta={
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "tokens_total": tokens_total,
                    },
                    reason="llm_turn",
                )
                await _emit_budget_snapshot(
                    entity_type="orchestrator",
                    entity_id=memory_orchestrator_id,
                    parent_entity_id=payload.runtime_run_id or payload.chat_id or memory_orchestrator_id,
                    role="memory",
                    limits=payload.memory_limits,
                    delta={
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "tokens_total": tokens_total,
                    },
                    reason=f"{component_name}_llm_turn",
                )

            writer = MemoryWriter(
                session=session,
                llm_client=llm_client,
                llm_event_sink=_on_llm_event,
                component_execution_ids=component_entity_ids,
            )
            component_prompts = await _load_memory_prompts(session)
            
            from app.runtime.contracts import PipelineStopReason
            
            terminal_reason = None
            if payload.terminal_reason:
                try:
                    terminal_reason = PipelineStopReason(payload.terminal_reason)
                except ValueError:
                    logger.warning("Unknown terminal reason: %s", payload.terminal_reason)
            
            memory_status = "completed"
            results: list[dict[str, Any]] = []
            failed_components: list[str] = []
            degraded_components: list[str] = []
            await _publish(
                RuntimeEvent.orchestrator_start(
                    orchestrator_id=memory_orchestrator_id,
                    run_id=payload.runtime_run_id or payload.chat_id,
                    role="memory",
                    context_snapshot=compact_snapshot(
                        inputs={
                            "user_request": payload.user_message,
                        },
                        limits=payload.memory_limits,
                        meta={
                            "role": "memory",
                            "components": list(component_entity_ids.keys()),
                        },
                    ),
                )
            )
            await _emit_budget_snapshot(
                entity_type="orchestrator",
                entity_id=memory_orchestrator_id,
                parent_entity_id=payload.runtime_run_id or payload.chat_id or memory_orchestrator_id,
                role="memory",
                limits=payload.memory_limits,
                reason="init",
            )
            try:
                for component_name, component_entity_id in component_entity_ids.items():
                    await _publish(
                        RuntimeEvent.agent_start(
                            agent_execution_id=component_entity_id,
                            parent_entity_id=memory_orchestrator_id,
                            parent_entity_type="orchestrator",
                            agent_slug=component_name,
                            context_snapshot=compact_snapshot(
                                inputs={
                                    "user_request": payload.user_message,
                                },
                                prompt=prompt_snapshot(
                                    component_prompts.get(component_name),
                                    payload.logging_level,
                                ),
                                limits=component_limits.get(component_name),
                                meta={
                                    "role": component_name,
                                    "agent_slug": component_name,
                                },
                            ),
                        )
                    )
                    await _emit_budget_snapshot(
                        entity_type="agent_execution",
                        entity_id=component_entity_id,
                        parent_entity_id=memory_orchestrator_id,
                        role=component_name,
                        limits=component_limits.get(component_name),
                        reason="init",
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
                        memory_component_entity_id(payload.runtime_run_id or payload.chat_id or "unknown", component_name, index),
                    )
                    component_status = str(item.get("status") or "completed")
                    # A skipped/degraded memory component is a completed
                    # post-response attempt with a non-fatal result.  It is
                    # not a HITL pause and must not put the trace stage on
                    # hold in the UI.
                    lifecycle_status = "failed" if component_status == "failed" else "completed"
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
                            entity_type="agent_execution",
                            entity_id=component_entity_id,
                            parent_entity_type="orchestrator",
                            parent_entity_id=memory_orchestrator_id,
                        )
                    )
                    if component_name in {"fact_extractor", "fact_compactor"}:
                        parsed = llm_structured_result.get(component_name) or {}
                        facts_payload = parsed.get("facts") if isinstance(parsed, dict) else None
                        await _publish(
                            RuntimeEvent.status(
                                "memory_facts_result",
                                parent_entity_type="orchestrator",
                                parent_entity_id=memory_orchestrator_id,
                                component_name=component_name,
                                facts=facts_payload if isinstance(facts_payload, list) else [],
                                entity_type="agent_execution",
                                entity_id=component_entity_id,
                            )
                        )
                    delta = {
                        "agent_steps": 1,
                        "wall_time_ms": int(item.get("duration_ms") or 0),
                    }
                    await _emit_budget_snapshot(
                        entity_type="agent_execution",
                        entity_id=component_entity_id,
                        parent_entity_id=memory_orchestrator_id,
                        role=component_name,
                        limits=component_limits.get(component_name),
                        delta=delta,
                        reason="component_result",
                    )
                    await _emit_budget_snapshot(
                        entity_type="orchestrator",
                        entity_id=memory_orchestrator_id,
                        parent_entity_id=payload.runtime_run_id or payload.chat_id or memory_orchestrator_id,
                        role="memory",
                        limits=payload.memory_limits,
                        delta=delta,
                        reason=f"{component_name}_component_result",
                    )
                    await _publish(
                        RuntimeEvent.agent_end(
                            agent_execution_id=component_entity_id,
                            parent_entity_id=memory_orchestrator_id,
                            parent_entity_type="orchestrator",
                            agent_slug=component_name,
                            status=lifecycle_status,
                            outcome=component_status,
                            summary=(
                                f"Новых фактов: {int(item.get('inserted_count') or 0)}"
                                if component_name in {"fact_extractor", "fact_compactor"}
                                else None
                            ),
                        )
                    )
            except Exception:
                memory_status = "failed"
                raise
            finally:
                for entity_id in list(budget_own.keys()):
                    entity_type = "orchestrator" if entity_id == memory_orchestrator_id else "agent_execution"
                    parent_entity_id = (
                        payload.runtime_run_id or payload.chat_id or memory_orchestrator_id
                        if entity_type == "orchestrator"
                        else memory_orchestrator_id
                    )
                    limits = (
                        payload.memory_limits
                        if entity_type == "orchestrator"
                        else component_limits.get("fact_extractor" if entity_id == component_entity_ids["fact_extractor"] else "fact_compactor")
                    )
                    role = "memory" if entity_type == "orchestrator" else ("fact_extractor" if entity_id == component_entity_ids["fact_extractor"] else "fact_compactor")
                    own_snapshot = {
                        key: int(value)
                        for key, value in budget_own.get(entity_id, {}).items()
                        if key in metric_keys
                    }
                    await _publish(
                        RuntimeEvent.budget_snapshot(
                            entity_type=entity_type,
                            entity_id=entity_id,
                        parent_entity_type="orchestrator" if entity_type == "agent_execution" else "run",
                            parent_entity_id=parent_entity_id,
                            own=own_snapshot,
                            limits=limits,
                            delta={},
                            reason="finalize",
                            role=role,
                        )
                    )
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
