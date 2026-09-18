"""
Memory writeback tasks — off-load memory finalization to Celery.

This module provides background task for persisting turn memory effects
(facts + summary) without blocking the SSE stream.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.memory import FactScope, FactSource, MemoryClaim, MemoryItem
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership, RAGStatus, Source
from app.models.collection import Collection
from app.models.glossary import GlossaryObservation
from app.workers.session_factory import get_worker_session
from app.workers.transaction_utils import checkpoint_commit
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.context_snapshot import compact_snapshot, prompt_snapshot
from app.runtime.memory.dto import SummaryDTO, FactDTO
from app.runtime.memory.fact_extractor import AgentResultSnippet, FactEvidence
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.writer import MemoryWriter
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.entity_ids import memory_component_entity_id, memory_orchestrator_id as make_memory_orchestrator_id
from app.services.system_llm_role_service import SystemLLMRoleService
from app.services.runtime_event_logger import RuntimeEventJournalFactory
from app.runtime.memory.evidence_feedback import (
    MemoryEvidenceEvaluator, MemoryEvidenceFeedbackService, bounded_document_evidence,
)


@shared_task(name="app.workers.tasks_memory.reextract_stale_document_memory", queue="maintenance.default")
def reextract_stale_document_memory(batch_size: int = 20) -> Dict[str, Any]:
    """Gradually refresh document memory withdrawn by a content contract change."""
    async def _reextract() -> Dict[str, Any]:
        from app.workers.tasks_shadow_document_memory import shadow_study_rag_document

        jobs: list[tuple[str, dict[str, str]]] = []
        async with get_worker_session() as session:
            rows = (await session.execute(
                select(RAGDocument, Source, RAGStatus)
                .join(Source, Source.source_id == RAGDocument.id)
                .outerjoin(MemoryClaim, MemoryClaim.document_id == RAGDocument.id)
                .outerjoin(GlossaryObservation, GlossaryObservation.document_id == RAGDocument.id)
                .outerjoin(RAGStatus, (RAGStatus.doc_id == RAGDocument.id)
                           & (RAGStatus.node_type == "memory") & (RAGStatus.node_key == "extract"))
                .where(
                    or_(MemoryClaim.state == "stale", GlossaryObservation.state == "stale"),
                    RAGDocument.status != "archived",
                    RAGDocument.s3_key_processed.is_not(None),
                )
                .order_by(RAGDocument.id)
            )).all()
            seen: set[UUID] = set()
            for document, source, status in rows:
                if document.id in seen or len(jobs) >= max(1, min(int(batch_size), 50)):
                    continue
                seen.add(document.id)
                metrics = dict(status.metrics_json or {}) if status is not None else {}
                if status is not None and status.status in {"queued", "processing"}:
                    continue
                if status is not None and status.status == "completed" and metrics.get("entity_graph_contract") is True:
                    continue
                tenant_id = source.tenant_id or document.tenant_id
                if tenant_id is None:
                    continue
                jobs.append((str(tenant_id), {
                    "source_id": str(document.id),
                }))
            await session.commit()
        for tenant_id, job in jobs:
            shadow_study_rag_document.delay(job, tenant_id)
        return {"queued": len(jobs)}

    return asyncio.run(_reextract())


@shared_task(name="app.workers.tasks_memory.index_memory_items", queue="memory")
def index_memory_items(memory_item_ids: List[str]) -> Dict[str, Any]:
    """Build/update the rebuildable company semantic index."""
    async def _index() -> Dict[str, Any]:
        async with get_worker_session() as session:
            ids = [UUID(str(value)) for value in memory_item_ids[:200]]
            rows = list((await session.execute(select(MemoryItem).where(MemoryItem.id.in_(ids)))).scalars().all())
            from app.runtime.memory.semantic_index import MemorySemanticIndex
            indexed = await MemorySemanticIndex(session).index_items(rows)
            return {"indexed": indexed}
    return asyncio.run(_index())


@shared_task(name="app.workers.tasks_memory.remove_memory_items", queue="memory")
def remove_memory_items(memory_item_ids: List[str]) -> Dict[str, Any]:
    async def _remove() -> Dict[str, Any]:
        async with get_worker_session() as session:
            ids = [UUID(str(value)) for value in memory_item_ids[:500]]
            from app.runtime.memory.semantic_index import MemorySemanticIndex
            removed = await MemorySemanticIndex(session).remove_items(ids)
            return {"removed": removed}
    return asyncio.run(_remove())


@shared_task(name="app.workers.tasks_memory.rebuild_memory_index", queue="memory")
def rebuild_memory_index() -> Dict[str, Any]:
    async def _rebuild() -> Dict[str, Any]:
        async with get_worker_session() as session:
            from app.runtime.memory.semantic_index import MemorySemanticIndex
            return {"indexed": await MemorySemanticIndex(session).rebuild()}
    return asyncio.run(_rebuild())


@shared_task(name="app.workers.tasks_memory.reconcile_memory_index", queue="maintenance.default")
def reconcile_memory_index() -> Dict[str, Any]:
    """Converge the derived Qdrant index to PostgreSQL after lost queue work."""
    async def _reconcile() -> Dict[str, Any]:
        from app.runtime.memory.semantic_index import MemorySemanticIndex

        indexed = removed = 0
        async with get_worker_session() as session:
            index = MemorySemanticIndex(session)
            for state in ("active", "uncertain"):
                cursor: UUID | None = None
                while True:
                    stmt = select(MemoryItem).where(MemoryItem.state == state)
                    if cursor is not None:
                        stmt = stmt.where(MemoryItem.id > cursor)
                    rows = list((await session.execute(stmt.order_by(MemoryItem.id).limit(200))).scalars().all())
                    if not rows:
                        break
                    indexed += await index.index_items(rows)
                    cursor = rows[-1].id
            stale_ids = list((await session.execute(select(MemoryItem.id).where(
                MemoryItem.state == "stale",
            ))).scalars().all())
            for start in range(0, len(stale_ids), 500):
                removed += await index.remove_items(stale_ids[start:start + 500])
        return {"indexed": indexed, "removed": removed}

    return asyncio.run(_reconcile())


@shared_task(name="app.workers.tasks_memory.refresh_memory_freshness", queue="maintenance.default")
def refresh_memory_freshness() -> Dict[str, Any]:
    """Mark source-backed knowledge stale when it has not been verified in time."""
    async def _refresh() -> Dict[str, Any]:
        # Procedures and policy constraints are intentionally short-lived:
        # using an old operational instruction is riskier than an old service
        # description.  RAG evidence can confirm and refresh an item later.
        max_age_days = {
            "procedure": 90, "rule": 120, "constraint": 120,
            "decision": 180, "description": 365, "relationship": 365,
        }
        stale_ids: list[UUID] = []
        now = datetime.now(timezone.utc)
        async with get_worker_session() as session:
            rows = list((await session.execute(select(MemoryItem).where(
                MemoryItem.state.in_(("active", "uncertain")),
            ))).scalars().all())
            for item in rows:
                age = max_age_days.get(item.item_type, 180)
                observed = item.last_verified_at or item.updated_at
                if observed < now - timedelta(days=age):
                    item.state = "stale"
                    stale_ids.append(item.id)
            await session.commit()
        if stale_ids:
            remove_memory_items.delay([str(item_id) for item_id in stale_ids])
        return {"stale": len(stale_ids)}

    return asyncio.run(_refresh())


@shared_task(name="app.workers.tasks_memory.reconcile_collection_memory_policy", queue="maintenance.default")
def reconcile_collection_memory_policy(collection_id: str) -> Dict[str, Any]:
    """Converge existing collection documents after its memory policy changes."""
    async def _reconcile() -> Dict[str, Any]:
        from app.runtime.memory.document_memory import retire_document_memory

        enabled_jobs: list[tuple[str, dict[str, str]]] = []
        stale_ids: set[UUID] = set()
        active_ids: set[UUID] = set()
        async with get_worker_session() as session:
            collection = await session.get(Collection, UUID(str(collection_id)))
            if collection is None:
                return {"processed": 0, "reason": "collection_not_found"}
            rows = (await session.execute(
                select(Source, RAGDocument)
                .join(DocumentCollectionMembership, DocumentCollectionMembership.source_id == Source.source_id)
                .join(RAGDocument, RAGDocument.id == Source.source_id)
                .where(DocumentCollectionMembership.collection_id == collection.id)
            )).all()
            for source, document in rows:
                meta = dict(source.meta or {})
                memory = dict(meta.get("memory") or {})
                explicit = memory.get("policy") == "explicit"
                enabled_membership = (await session.execute(
                    select(func.count(DocumentCollectionMembership.id))
                    .join(Collection, Collection.id == DocumentCollectionMembership.collection_id)
                    .where(
                        DocumentCollectionMembership.source_id == source.source_id,
                        Collection.memory_enabled.is_(True),
                    )
                )).scalar_one() > 0
                enabled = bool(memory.get("enabled")) if explicit else enabled_membership
                if not explicit:
                    memory["enabled"] = enabled
                    memory["policy"] = "collection"
                    meta["memory"] = memory
                    source.meta = meta
                if enabled and document.s3_key_processed and document.status != "archived":
                    enabled_jobs.append((str(document.tenant_id), {
                        "source_id": str(document.id), "canonical_key": str(document.s3_key_processed),
                    }))
                elif not enabled:
                    states = await retire_document_memory(session, document_id=document.id)
                    stale_ids.update(item_id for item_id, state in states.items() if state == "stale")
                    active_ids.update(item_id for item_id, state in states.items() if state in {"active", "uncertain"})
            await session.commit()
        if stale_ids:
            remove_memory_items.delay([str(item_id) for item_id in stale_ids])
        if active_ids:
            index_memory_items.delay([str(item_id) for item_id in active_ids])
        if enabled_jobs:
            from app.workers.tasks_shadow_document_memory import shadow_study_rag_document
            for tenant_id, job in enabled_jobs:
                shadow_study_rag_document.delay(job, tenant_id)
        return {"processed": len(enabled_jobs) + len(stale_ids) + len(active_ids), "enabled": len(enabled_jobs)}

    return asyncio.run(_reconcile())

logger = get_logger(__name__)


@shared_task(name="app.workers.tasks_memory.evaluate_memory_rag_evidence", queue="memory")
def evaluate_memory_rag_evidence(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate recalled memory against one successful RAG result after a turn."""
    import asyncio

    async def _evaluate() -> Dict[str, Any]:
        tenant_id = UUID(str(payload["tenant_id"]))
        tool_call_id = str(payload["tool_call_id"])
        # Pipeline sends an already bounded, documentary-only payload. Keep a
        # legacy fallback for tasks queued before this contract existed.
        raw_evidence = payload.get("evidence")
        evidence = list(raw_evidence)[:8] if isinstance(raw_evidence, list) else bounded_document_evidence(payload.get("result"))
        item_ids = [UUID(str(value)) for value in payload.get("memory_item_ids") or []]
        claim_ids = [UUID(str(value)) for value in payload.get("claim_ids") or []]
        if not evidence or not item_ids or not claim_ids:
            return {"evaluated": 0, "reason": "no_evidence_or_items"}
        reextract_document_ids: set[UUID] = set()
        reindex_item_ids: set[UUID] = set()
        evaluated = 0
        async with get_worker_session() as session:
            from app.core.di import get_llm_client
            evaluator = MemoryEvidenceEvaluator(session=session, llm_client=get_llm_client())
            feedback = MemoryEvidenceFeedbackService(session)
            visible_claims = (await session.execute(
                select(MemoryClaim).join(RAGDocument, RAGDocument.id == MemoryClaim.document_id).where(
                    MemoryClaim.id.in_(claim_ids[:24]), MemoryClaim.memory_item_id.in_(item_ids[:12]),
                    MemoryClaim.state == "active",
                    or_(MemoryClaim.visibility_tenant_id.is_(None), MemoryClaim.visibility_tenant_id == tenant_id),
                    or_(RAGDocument.scope == "global", RAGDocument.tenant_id == tenant_id),
                    RAGDocument.status != "archived",
                )
            )).scalars().all()
            requested_claims_by_item: dict[UUID, UUID] = {}
            for raw_item_id, raw_claim_id in dict(payload.get("selected_claim_ids_by_item") or {}).items():
                try:
                    requested_claims_by_item[UUID(str(raw_item_id))] = UUID(str(raw_claim_id))
                except (TypeError, ValueError):
                    continue
            claims_by_id = {claim.id: claim for claim in visible_claims}
            claims_by_item: dict[UUID, MemoryClaim] = {}
            for claim in visible_claims:
                requested = requested_claims_by_item.get(claim.memory_item_id)
                if requested is not None:
                    selected = claims_by_id.get(requested)
                    if selected is not None:
                        claims_by_item[claim.memory_item_id] = selected
                    continue
                # Compatibility for jobs queued before selected claim ids.
                # Deterministic ordering avoids a database-dependent choice.
                current = claims_by_item.get(claim.memory_item_id)
                if current is None or (claim.confidence, claim.updated_at, str(claim.id)) > (
                    current.confidence, current.updated_at, str(current.id)
                ):
                    claims_by_item[claim.memory_item_id] = claim
            for item_id, claim in list(claims_by_item.items())[:12]:
                item = (await session.execute(select(MemoryItem).where(MemoryItem.id == item_id))).scalar_one_or_none()
                if item is None:
                    continue
                if await feedback.already_evaluated(memory_item_id=item.id, tool_call_id=tool_call_id):
                    continue
                decision = await evaluator.evaluate(item=item, content=dict(claim.content or {}), evidence=evidence, tenant_id=tenant_id)
                applied, documents = await feedback.apply(item=item, claim=claim, tool_call_id=tool_call_id, decision=decision)
                if applied:
                    evaluated += 1
                    reindex_item_ids.add(item.id)
                    reextract_document_ids.update(documents)
            await session.commit()
        if reindex_item_ids:
            from app.workers.tasks_memory import index_memory_items
            index_memory_items.delay([str(item_id) for item_id in reindex_item_ids])
        if reextract_document_ids:
            from app.models.rag import RAGDocument
            async with get_worker_session() as session:
                rows = (await session.execute(select(RAGDocument).where(
                    RAGDocument.id.in_(reextract_document_ids),
                ))).scalars().all()
                jobs = [
                    (str(row.tenant_id), {"source_id": str(row.id), "canonical_key": row.s3_key_processed})
                    for row in rows if row.s3_key_processed and row.tenant_id
                ]
            from app.workers.tasks_shadow_document_memory import shadow_study_rag_document
            for document_tenant_id, job in jobs:
                shadow_study_rag_document.delay(job, document_tenant_id)
        return {"evaluated": evaluated, "reextract_documents": len(reextract_document_ids)}

    return asyncio.run(_evaluate())


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
    # TurnPreflight candidates are hints for FactExtractor, not durable facts.
    # They must survive the default Celery handoff so inline and async
    # finalization apply the same evidence-validation path.
    preflight_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    
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
        preflight_candidates=list(payload.preflight_candidates),
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
        metric_keys = ("agent_steps", "tool_calls", "tokens_in", "tokens_out", "tokens_total", "retries", "wall_time_ms")

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
                # Reconciliation uses flushes so facts are visible within the
                # worker transaction, but a Celery session is rolled back on
                # close unless this task owns an explicit commit boundary.
                # Persist the completed writeback before emitting diagnostics.
                await checkpoint_commit(session, "finalize_memory", "facts_writeback")
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
                    for decision in item.get("decisions") or []:
                        if not isinstance(decision, dict):
                            continue
                        decision_payload = dict(decision)
                        decision_payload.pop("stage", None)
                        await _publish(
                            RuntimeEvent.status(
                                "memory_candidate_decision",
                                **decision_payload,
                                entity_type="agent_execution",
                                entity_id=component_entity_id,
                                parent_entity_type="orchestrator",
                                parent_entity_id=memory_orchestrator_id,
                            )
                        )
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
                            facts=item.get("facts", []),
                            decision_counts=item.get("decision_counts", {}),
                            entity_type="agent_execution",
                            entity_id=component_entity_id,
                            parent_entity_type="orchestrator",
                            parent_entity_id=memory_orchestrator_id,
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
