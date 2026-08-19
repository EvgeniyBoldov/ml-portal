"""MemoryWriter — write path at turn end.

Takes the finished `TurnMemory` plus raw turn text and persists memory effects.
Failure policy: write-side failures must not break user turn completion.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Awaitable, Callable, List, Optional, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.core.prometheus_metrics import memory_writer_component_status_total
from app.models.chat import Chats
from app.models.memory import FactScope, FactSource
from app.models.sandbox import SandboxBranch
from app.runtime.memory.fact_extractor import (
    FactExtractor,
    FactEvidence,
    KnownFactSnippet,
)
from app.runtime.memory.fact_compactor import FactCompactor
from app.runtime.memory.fact_reconciler import FactReconciler
from app.runtime.memory.glossary_reconciler import GlossaryReconciler
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.sandbox_overlays import merge_extracted
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.service import MemoryService
from app.runtime.contracts import PipelineStopReason
from app.runtime.events import RuntimeEvent

logger = get_logger(__name__)


_TRIVIAL_UTTERANCES = {
    "ok", "okay", "ок", "ага", "угу", "спасибо", "thanks", "thank you", "понял", "понятно",
}


@dataclass
class MemoryWriteContext:
    memory: TurnMemory
    user_message: str
    assistant_final: str
    skip_llm_helpers: bool
    persist_chat_scoped: bool
    sandbox_branch_id: Optional[UUID]
    terminal_reason: Optional[PipelineStopReason] = None
    sandbox_overrides: Optional[dict] = None
    fact_candidates: Optional[List[Any]] = None


@dataclass(frozen=True)
class MemoryWriteResult:
    component_name: str
    status: str  # ok|skipped|degraded|failed
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: int = 0

    def compact_view(self) -> dict:
        return {
            "component_name": self.component_name,
            "status": self.status,
            "inserted_count": self.inserted_count,
            "updated_count": self.updated_count,
            "skipped_count": self.skipped_count,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


class MemoryWriteComponent(Protocol):
    name: str

    async def write(self, ctx: MemoryWriteContext) -> MemoryWriteResult: ...


class MemoryWriter:
    """Persist a turn's memory effects."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        llm_event_sink: Optional[Callable[[str, RuntimeEvent], Awaitable[None]]] = None,
        component_execution_ids: Optional[dict[str, str]] = None,
    ) -> None:
        self._session = session
        self._fact_store = FactStore(session)
        self._memory_service = MemoryService(fact_store=self._fact_store)
        self._extractor = FactExtractor(session=session, llm_client=llm_client)
        self._fact_compactor = FactCompactor(session=session, llm_client=llm_client)
        self._fact_reconciler = FactReconciler(session)
        self._glossary_reconciler = GlossaryReconciler(session)
        self._llm_event_sink = llm_event_sink
        self._component_execution_ids = dict(component_execution_ids or {})
        # Single AsyncSession is not concurrency-safe for writes.
        # We still parallelize LLM-heavy component logic and serialize DB writes.
        self._db_write_lock = asyncio.Lock()
        self._components: List[MemoryWriteComponent] = [
            _FactExtractionMemoryWriteComponent(self),
            _FactCompactionMemoryWriteComponent(self),
        ]

    async def finalize(
        self,
        *,
        memory: TurnMemory,
        user_message: str,
        assistant_final: Optional[str],
        terminal_reason: Optional[PipelineStopReason] = None,
        sandbox_overrides: Optional[dict] = None,
    ) -> None:
        """Write durable facts with component diagnostics."""
        context = MemoryWriteContext(
            memory=memory,
            user_message=user_message,
            assistant_final=assistant_final or "",
            skip_llm_helpers=self._should_skip_llm_helpers(
                memory, user_message, terminal_reason
            ),
            persist_chat_scoped=False,
            sandbox_branch_id=_resolve_sandbox_branch_id(sandbox_overrides),
            terminal_reason=terminal_reason,
            sandbox_overrides=sandbox_overrides,
        )
        # Sandbox upload chats are real ``chats`` rows for artifact ownership,
        # but they must never turn a sandbox memory write into durable user or
        # tenant memory.
        context = replace(
            context,
            persist_chat_scoped=(
                context.sandbox_branch_id is None and await self._chat_exists(memory.chat_id)
            ),
        )
        if not context.persist_chat_scoped and context.sandbox_branch_id is None:
            return

        results: list[MemoryWriteResult] = []
        for component in self._components:
            results.append(
                await self._run_component(component=component, context=context, chat_id=memory.chat_id)
            )

        self._attach_write_diagnostics(memory=memory, results=results)

    async def _run_component(
        self,
        *,
        component: MemoryWriteComponent,
        context: MemoryWriteContext,
        chat_id,
    ) -> MemoryWriteResult:
        started = monotonic()
        try:
            result = await component.write(context)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MemoryWriter component '%s' failed for chat=%s: %s",
                component.name,
                chat_id,
                exc,
            )
            result = MemoryWriteResult(
                component_name=component.name,
                status="failed",
                error_code="memory_component_error",
                error_message=str(exc)[:500],
            )
        elapsed_ms = int((monotonic() - started) * 1000)
        return MemoryWriteResult(
            component_name=result.component_name,
            status=result.status,
            inserted_count=result.inserted_count,
            updated_count=result.updated_count,
            skipped_count=result.skipped_count,
            error_code=result.error_code,
            error_message=result.error_message,
            duration_ms=elapsed_ms,
        )

    # ---------------------------------------------------------------- facts

    async def _extract_facts(
        self,
        memory: TurnMemory,
        user_message: str,
        sandbox_overrides: Optional[dict] = None,
        persist_chat_scoped: bool = True,
    ) -> List[Any]:
        known = [
            KnownFactSnippet(subject=s, value=v)
            for s, v in memory.iter_known_subjects()
        ]
        evidence = [
            FactEvidence(
                source_id="user_message",
                source_type="user_message",
                source_ref=str(memory.fact_run_ref or memory.chat_id or "request"),
                text=user_message,
                label="user message",
            ),
            *memory.fact_evidence,
        ]
        return await self._extractor.extract(
            user_message=user_message,
            evidence=evidence,
            known_facts=known,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            chat_id=memory.chat_id,
            sandbox_overrides=sandbox_overrides,
            llm_event_sink=(
                (lambda event: self._llm_event_sink("fact_extractor", event))
                if self._llm_event_sink
                else None
            ),
            agent_execution_id=self._component_execution_ids.get("fact_extractor"),
        )

    @staticmethod
    def _project_candidate_facts(memory: TurnMemory) -> list[FactDTO]:
        evidence_by_id = {item.source_id: item for item in memory.fact_evidence}
        facts: list[FactDTO] = []
        for candidate in memory.project_memory_candidates:
            evidence = [
                evidence_by_id[call_id].model_dump()
                for call_id in candidate.evidence_call_ids
                if call_id in evidence_by_id
            ]
            if not evidence:
                continue
            facts.append(FactDTO(
                scope=FactScope.PROJECT,
                subject=candidate.subject,
                value=candidate.value,
                source=FactSource.TOOL_RESULT,
                tenant_id=memory.tenant_id,
                confidence=1.0,
                metadata={
                    "project_key": candidate.project_key,
                    "project_aliases": list(candidate.aliases),
                    "project_memory_marked": True,
                    "evidence": evidence,
                },
            ))
        return facts

    async def _compact_and_write_facts(
        self,
        memory: TurnMemory,
        candidates: List[Any],
        sandbox_overrides: Optional[dict] = None,
        persist_chat_scoped: bool = True,
    ) -> int:
        branch_id = _resolve_sandbox_branch_id(sandbox_overrides)
        project_candidates = self._project_candidate_facts(memory)
        all_candidates = [*candidates, *project_candidates]
        if not all_candidates:
            return 0
        project_keys = [
            str(item.metadata.get("project_key") or "")
            for item in all_candidates
            if getattr(item, "scope", None) == FactScope.PROJECT
        ]
        if memory.chat_id is None or not persist_chat_scoped:
            if branch_id is None:
                return 0
            current = list(getattr(memory.durable_snapshot, "entries", ()) or ())
            compacted = await self._fact_compactor.compact(
                candidates=all_candidates,
                current_facts=current,
                user_id=memory.user_id,
                tenant_id=memory.tenant_id,
                chat_id=memory.chat_id,
                sandbox_overrides=sandbox_overrides,
                event_sink=(lambda event: self._llm_event_sink("fact_compactor", event)) if self._llm_event_sink else None,
            )
            branch_facts = [item for item in compacted if item.kind != "glossary"]
            return await self._write_branch_facts(
                branch_id=branch_id,
                facts=branch_facts,
                base=current,
            )
        async with self._db_write_lock:
            await self._fact_reconciler.ensure_projects(all_candidates)
            current = await self._fact_reconciler.current_for(
                user_id=memory.user_id,
                tenant_id=memory.tenant_id,
                project_keys=project_keys,
            )
            current.extend(await self._glossary_reconciler.current_for(
                user_id=memory.user_id,
                tenant_id=memory.tenant_id,
            ))
            compacted = await self._fact_compactor.compact(
                candidates=all_candidates,
                current_facts=current,
                user_id=memory.user_id,
                tenant_id=memory.tenant_id,
                chat_id=memory.chat_id,
                sandbox_overrides=sandbox_overrides,
                event_sink=(lambda event: self._llm_event_sink("fact_compactor", event)) if self._llm_event_sink else None,
            )
            saved = await self._fact_reconciler.apply(
                candidates=[item for item in compacted if item.kind != "glossary"],
                user_id=memory.user_id,
                tenant_id=memory.tenant_id,
            )
            saved += await self._glossary_reconciler.apply(
                candidates=[item for item in compacted if item.kind == "glossary"],
                user_id=memory.user_id,
                tenant_id=memory.tenant_id,
            )
        return saved

    async def _chat_exists(self, chat_id) -> bool:
        if chat_id is None:
            return False
        row = await self._session.execute(select(Chats.id).where(Chats.id == chat_id))
        return row.scalar_one_or_none() is not None

    async def _write_branch_facts(self, *, branch_id: UUID, facts: List[Any], base: List[Any]) -> int:
        row = await self._session.execute(select(SandboxBranch).where(SandboxBranch.id == branch_id))
        branch = row.scalar_one_or_none()
        if branch is None:
            logger.warning("MemoryWriter: sandbox branch %s is missing; facts were not persisted", branch_id)
            return 0
        branch.fact_overrides_json = merge_extracted(branch.fact_overrides_json, facts, base=base)
        branch.artifacts_updated_at = datetime.now(timezone.utc)
        self._session.add(branch)
        await self._session.flush()
        return len(facts)

    @staticmethod
    def _should_skip_llm_helpers(
        memory: TurnMemory, user_message: str, terminal_reason: Optional[PipelineStopReason]
    ) -> bool:
        """Avoid extra LLM helper calls on known degraded turns."""
        # Typed signal: skip on budget exceeded only.
        if terminal_reason == PipelineStopReason.BUDGET_EXCEEDED:
            return True
        # Trivial acknowledgement turns do not provide stable memory signal.
        if _is_trivial_utterance(user_message):
            return True

        failed_results = [r for r in memory.agent_results if not r.success]
        if not failed_results:
            return False
        if any(r.success for r in memory.agent_results):
            return False

        for result in failed_results:
            err_text = f"{result.summary}\n{result.agent}".lower()
            if _looks_non_retryable_limit_error(err_text):
                return True
        return False

    @staticmethod
    def _attach_write_diagnostics(*, memory: TurnMemory, results: List[MemoryWriteResult]) -> None:
        for item in results:
            try:
                memory_writer_component_status_total.labels(
                    component_name=item.component_name or "unknown",
                    status=item.status or "unknown",
                ).inc()
            except Exception:
                pass
        payload = {
            "results": [item.compact_view() for item in results],
            "failed_components": [item.component_name for item in results if item.status == "failed"],
            "degraded_components": [item.component_name for item in results if item.status == "degraded"],
        }
        memory.memory_diagnostics = dict(memory.memory_diagnostics or {})
        memory.memory_diagnostics["memory_write_status"] = payload


class _FactExtractionMemoryWriteComponent:
    name = "fact_extractor"

    def __init__(self, owner: MemoryWriter) -> None:
        self._owner = owner

    async def write(self, ctx: MemoryWriteContext) -> MemoryWriteResult:
        if ctx.skip_llm_helpers:
            return MemoryWriteResult(component_name=self.name, status="skipped", skipped_count=1)
        candidates = await self._owner._extract_facts(
            ctx.memory,
            ctx.user_message,
            ctx.sandbox_overrides,
            ctx.persist_chat_scoped,
        )
        ctx.fact_candidates = candidates
        if not ctx.persist_chat_scoped and not ctx.sandbox_branch_id:
            return MemoryWriteResult(
                component_name=self.name,
                status="degraded",
                inserted_count=len(candidates),
                error_code="sandbox_persist_skipped",
                error_message="Chat-scoped persistence skipped: sandbox chat is not stored in chats table",
            )
        return MemoryWriteResult(component_name=self.name, status="ok", inserted_count=len(candidates))


class _FactCompactionMemoryWriteComponent:
    name = "fact_compactor"

    def __init__(self, owner: MemoryWriter) -> None:
        self._owner = owner

    async def write(self, ctx: MemoryWriteContext) -> MemoryWriteResult:
        if ctx.skip_llm_helpers:
            return MemoryWriteResult(component_name=self.name, status="skipped", skipped_count=1)
        saved = await self._owner._compact_and_write_facts(
            ctx.memory,
            list(ctx.fact_candidates or []),
            ctx.sandbox_overrides,
            ctx.persist_chat_scoped,
        )
        if not ctx.persist_chat_scoped and not ctx.sandbox_branch_id:
            return MemoryWriteResult(
                component_name=self.name,
                status="degraded",
                inserted_count=saved,
                error_code="sandbox_persist_skipped",
                error_message="Chat-scoped persistence skipped: sandbox chat is not stored in chats table",
            )
        return MemoryWriteResult(component_name=self.name, status="ok", inserted_count=saved)


def _resolve_sandbox_branch_id(sandbox_overrides: Optional[dict]) -> Optional[UUID]:
    raw = (sandbox_overrides or {}).get("sandbox_branch_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _fact_to_artifact_row(fact: Any) -> dict[str, Any]:
    scope_value = getattr(fact, "scope", FactScope.USER)
    if hasattr(scope_value, "value"):
        scope_value = scope_value.value
    source_value = getattr(fact, "source", "user_utterance")
    if hasattr(source_value, "value"):
        source_value = source_value.value
    return {
        "scope": str(scope_value),
        "subject": str(getattr(fact, "subject", "")),
        "value": str(getattr(fact, "value", "")),
        "source": str(source_value),
        "confidence": float(getattr(fact, "confidence", 1.0)),
        "source_ref": getattr(fact, "source_ref", None),
    }


def _looks_non_retryable_limit_error(text: str) -> bool:
    patterns = (
        "error code: 413",
        "request too large",
        "rate_limit_exceeded",
        "tokens per minute",
        "context_length_exceeded",
        "maximum context length",
        "tool_use_failed",
        "tool choice is none, but model called a tool",
    )
    lowered = (text or "").lower()
    return any(p in lowered for p in patterns)


def _is_trivial_utterance(text: str) -> bool:
    normalized = " ".join((text or "").strip().lower().split())
    if not normalized:
        return False
    return normalized in _TRIVIAL_UTTERANCES
