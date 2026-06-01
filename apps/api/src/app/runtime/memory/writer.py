"""MemoryWriter — write path at turn end.

Takes the finished `TurnMemory` plus raw turn text and persists memory effects.
Failure policy: write-side failures must not break user turn completion.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable, List, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.core.prometheus_metrics import memory_writer_component_status_total
from app.models.chat import Chats
from app.models.memory import FactScope
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.fact_extractor import (
    FactExtractor,
    KnownFactSnippet,
)
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.summary_compactor import SummaryCompactor
from app.runtime.memory.summary_store import SummaryStore
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.user_facts_service import LongTermFactsService
from app.runtime.contracts import PipelineStopReason

logger = get_logger(__name__)


RAW_TAIL_MAX_CHARS = 2000
_TRIVIAL_UTTERANCES = {
    "ok", "okay", "ок", "ага", "угу", "спасибо", "thanks", "thank you", "понял", "понятно",
}


@dataclass(frozen=True)
class MemoryWriteContext:
    memory: TurnMemory
    user_message: str
    assistant_final: str
    skip_llm_helpers: bool
    persist_chat_scoped: bool
    terminal_reason: Optional[PipelineStopReason] = None
    sandbox_overrides: Optional[dict] = None
    raw_tail_max_chars: int = RAW_TAIL_MAX_CHARS


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
        llm_event_callback: Optional[Callable[[str, dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self._session = session
        self._fact_store = FactStore(session)
        self._summary_store = SummaryStore(session)
        self._extractor = FactExtractor(session=session, llm_client=llm_client)
        self._compactor = SummaryCompactor(session=session, llm_client=llm_client)
        self._llm_event_callback = llm_event_callback
        # Single AsyncSession is not concurrency-safe for writes.
        # We still parallelize LLM-heavy component logic and serialize DB writes.
        self._db_write_lock = asyncio.Lock()
        self._components: List[MemoryWriteComponent] = [
            _FactMemoryWriteComponent(self),
            _ConversationMemoryWriteComponent(self),
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
        """Write facts + summary with component diagnostics."""
        context = MemoryWriteContext(
            memory=memory,
            user_message=user_message,
            assistant_final=assistant_final or "",
            skip_llm_helpers=self._should_skip_llm_helpers(
                memory, user_message, terminal_reason
            ),
            persist_chat_scoped=await self._chat_exists(memory.chat_id),
            terminal_reason=terminal_reason,
            sandbox_overrides=sandbox_overrides,
            raw_tail_max_chars=_resolve_raw_tail_max_chars(sandbox_overrides),
        )

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

    async def _write_summary_fallback_only(
        self,
        *,
        memory: TurnMemory,
        user_message: str,
        assistant_final: str,
        raw_tail_max_chars: int = RAW_TAIL_MAX_CHARS,
    ) -> None:
        assert memory.chat_id is not None
        fallback = SummaryDTO(
            chat_id=memory.chat_id,
            goals=list(memory.summary.goals),
            done=list(memory.summary.done),
            entities=dict(memory.summary.entities),
            open_questions=list(memory.summary.open_questions),
            raw_tail=_rebuild_raw_tail(
                memory.summary.raw_tail,
                user_message,
                assistant_final,
                max_chars=raw_tail_max_chars,
            ),
            last_updated_turn=memory.turn_number,
        )
        async with self._db_write_lock:
            await self._summary_store.save(fallback)

    # ---------------------------------------------------------------- facts

    async def _write_facts(
        self,
        memory: TurnMemory,
        user_message: str,
        sandbox_overrides: Optional[dict] = None,
        persist_chat_scoped: bool = True,
    ) -> int:
        known = [
            KnownFactSnippet(subject=s, value=v)
            for s, v in memory.iter_known_subjects()
        ]
        new_facts = await self._extractor.extract(
            user_message=user_message,
            agent_results=memory.agent_results,
            known_facts=known,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            chat_id=memory.chat_id,
            sandbox_overrides=sandbox_overrides,
            llm_event_callback=(
                (lambda payload: self._llm_event_callback("facts", payload))
                if self._llm_event_callback
                else None
            ),
        )
        long_term = LongTermFactsService(
            fact_store=self._fact_store,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
        )
        if memory.chat_id is None or not persist_chat_scoped:
            # Sandbox-only flow: keep extraction/trace visibility, skip DB writes.
            return len(new_facts)
        async with self._db_write_lock:
            long_term_saved = await long_term.save_for_runtime(facts=new_facts)
            for fact in new_facts:
                if fact.scope in (FactScope.USER, FactScope.TENANT):
                    continue
                await self._fact_store.upsert_with_supersede(fact)
        return max(long_term_saved, len(new_facts))

    # -------------------------------------------------------------- summary

    async def _write_summary(
        self,
        memory: TurnMemory,
        user_message: str,
        assistant_final: str,
        sandbox_overrides: Optional[dict] = None,
        raw_tail_max_chars: int = RAW_TAIL_MAX_CHARS,
        persist_chat_scoped: bool = True,
    ) -> bool:
        new_summary = await self._compactor.compact(
            previous=memory.summary,
            user_message=user_message,
            assistant_final=assistant_final,
            agent_results=memory.agent_results,
            turn_number=memory.turn_number,
            chat_id=memory.chat_id,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
            sandbox_overrides=sandbox_overrides,
            llm_event_callback=(
                (lambda payload: self._llm_event_callback("conversation", payload))
                if self._llm_event_callback
                else None
            ),
        )
        # Maintain raw_tail locally — the LLM is explicitly told not to
        # touch it. We append user+assistant pair to the existing tail
        # and clip from the front to respect the char budget.
        new_summary.raw_tail = _rebuild_raw_tail(
            memory.summary.raw_tail,
            user_message,
            assistant_final,
            max_chars=raw_tail_max_chars,
        )
        if memory.chat_id is None or not persist_chat_scoped:
            # Sandbox-only flow: keep compactor execution/trace, skip summary persistence.
            return False
        new_summary.chat_id = memory.chat_id

        async with self._db_write_lock:
            await self._summary_store.save(new_summary)
        return True

    async def _chat_exists(self, chat_id) -> bool:
        if chat_id is None:
            return False
        row = await self._session.execute(select(Chats.id).where(Chats.id == chat_id))
        return row.scalar_one_or_none() is not None

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


class _FactMemoryWriteComponent:
    name = "facts"

    def __init__(self, owner: MemoryWriter) -> None:
        self._owner = owner

    async def write(self, ctx: MemoryWriteContext) -> MemoryWriteResult:
        if ctx.skip_llm_helpers:
            return MemoryWriteResult(component_name=self.name, status="skipped", skipped_count=1)
        inserted = await self._owner._write_facts(
            ctx.memory,
            ctx.user_message,
            ctx.sandbox_overrides,
            ctx.persist_chat_scoped,
        )
        if not ctx.persist_chat_scoped:
            return MemoryWriteResult(component_name=self.name, status="degraded", inserted_count=inserted)
        return MemoryWriteResult(component_name=self.name, status="ok", inserted_count=inserted)


class _ConversationMemoryWriteComponent:
    name = "conversation"

    def __init__(self, owner: MemoryWriter) -> None:
        self._owner = owner

    async def write(self, ctx: MemoryWriteContext) -> MemoryWriteResult:
        if ctx.skip_llm_helpers:
            await self._owner._write_summary_fallback_only(
                memory=ctx.memory,
                user_message=ctx.user_message,
                assistant_final=ctx.assistant_final,
                raw_tail_max_chars=ctx.raw_tail_max_chars,
            )
            return MemoryWriteResult(component_name=self.name, status="degraded", updated_count=1)

        persisted = await self._owner._write_summary(
            ctx.memory,
            ctx.user_message,
            ctx.assistant_final,
            ctx.sandbox_overrides,
            ctx.raw_tail_max_chars,
            ctx.persist_chat_scoped,
        )
        if not persisted:
            return MemoryWriteResult(component_name=self.name, status="degraded", updated_count=1)
        return MemoryWriteResult(component_name=self.name, status="ok", updated_count=1)


def _rebuild_raw_tail(
    previous_tail: str,
    user_message: str,
    assistant_final: str,
    *,
    max_chars: int = RAW_TAIL_MAX_CHARS,
) -> str:
    """Append the current turn to the tail and clip from the front.

    Format is deliberately minimal — this buffer is a cheap fallback
    for small-context local models, not a formatted transcript.
    """
    pieces = []
    if previous_tail:
        pieces.append(previous_tail.rstrip())
    if user_message:
        pieces.append(f"user: {user_message.strip()}")
    if assistant_final:
        pieces.append(f"assistant: {assistant_final.strip()}")
    joined = "\n".join(pieces)
    if len(joined) <= max_chars:
        return joined
    # Clip from the front — keep the most recent content.
    return joined[-max_chars:]


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


def _resolve_raw_tail_max_chars(sandbox_overrides: Optional[dict]) -> int:
    value = None
    cfg = sandbox_overrides or {}
    if isinstance(cfg, dict):
        runtime_cfg = cfg.get("runtime")
        memory_cfg = cfg.get("memory")
        if isinstance(runtime_cfg, dict):
            value = runtime_cfg.get("memory_raw_tail_max_chars", value)
        if isinstance(memory_cfg, dict):
            value = memory_cfg.get("raw_tail_max_chars", value)
    if isinstance(value, int) and value >= 256:
        return value
    return RAW_TAIL_MAX_CHARS
