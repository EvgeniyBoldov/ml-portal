"""MemoryWriter — write path at turn end.

Takes the finished `TurnMemory` plus raw turn text and persists memory effects.
Failure policy: write-side failures must not break user turn completion.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import List, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
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


@dataclass(frozen=True)
class MemoryWriteContext:
    memory: TurnMemory
    user_message: str
    assistant_final: str
    skip_llm_helpers: bool
    terminal_reason: Optional[PipelineStopReason] = None


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
    ) -> None:
        self._session = session
        self._fact_store = FactStore(session)
        self._summary_store = SummaryStore(session)
        self._extractor = FactExtractor(session=session, llm_client=llm_client)
        self._compactor = SummaryCompactor(session=session, llm_client=llm_client)
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
    ) -> None:
        """Write facts + summary with component diagnostics."""
        if memory.chat_id is None:
            return

        context = MemoryWriteContext(
            memory=memory,
            user_message=user_message,
            assistant_final=assistant_final or "",
            skip_llm_helpers=self._should_skip_llm_helpers(
                memory, assistant_final or "", terminal_reason
            ),
            terminal_reason=terminal_reason,
        )

        results: List[MemoryWriteResult] = []
        for component in self._components:
            started = monotonic()
            try:
                result = await component.write(context)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MemoryWriter component '%s' failed for chat=%s: %s",
                    component.name,
                    memory.chat_id,
                    exc,
                )
                result = MemoryWriteResult(
                    component_name=component.name,
                    status="failed",
                    error_code="memory_component_error",
                    error_message=str(exc)[:500],
                )
            elapsed_ms = int((monotonic() - started) * 1000)
            results.append(
                MemoryWriteResult(
                    component_name=result.component_name,
                    status=result.status,
                    inserted_count=result.inserted_count,
                    updated_count=result.updated_count,
                    skipped_count=result.skipped_count,
                    error_code=result.error_code,
                    error_message=result.error_message,
                    duration_ms=elapsed_ms,
                )
            )

        self._attach_write_diagnostics(memory=memory, results=results)

    async def _write_summary_fallback_only(
        self,
        *,
        memory: TurnMemory,
        user_message: str,
        assistant_final: str,
    ) -> None:
        assert memory.chat_id is not None
        fallback = SummaryDTO(
            chat_id=memory.chat_id,
            goals=list(memory.summary.goals),
            done=list(memory.summary.done),
            entities=dict(memory.summary.entities),
            open_questions=list(memory.summary.open_questions),
            raw_tail=_rebuild_raw_tail(memory.summary.raw_tail, user_message, assistant_final),
            last_updated_turn=memory.turn_number,
        )
        await self._summary_store.save(fallback)

    # ---------------------------------------------------------------- facts

    async def _write_facts(
        self,
        memory: TurnMemory,
        user_message: str,
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
        )
        long_term = LongTermFactsService(
            fact_store=self._fact_store,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
        )
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
    ) -> None:
        assert memory.chat_id is not None  # guarded by caller

        new_summary = await self._compactor.compact(
            previous=memory.summary,
            user_message=user_message,
            assistant_final=assistant_final,
            agent_results=memory.agent_results,
            turn_number=memory.turn_number,
            chat_id=memory.chat_id,
            user_id=memory.user_id,
            tenant_id=memory.tenant_id,
        )
        # Maintain raw_tail locally — the LLM is explicitly told not to
        # touch it. We append user+assistant pair to the existing tail
        # and clip from the front to respect the char budget.
        new_summary.raw_tail = _rebuild_raw_tail(
            memory.summary.raw_tail, user_message, assistant_final,
        )
        new_summary.chat_id = memory.chat_id

        await self._summary_store.save(new_summary)

    @staticmethod
    def _should_skip_llm_helpers(
        memory: TurnMemory, assistant_final: str, terminal_reason: Optional[PipelineStopReason]
    ) -> bool:
        """Avoid extra LLM helper calls on known degraded turns."""
        # Typed signal: skip on loop detection or budget exceeded
        if terminal_reason in (PipelineStopReason.LOOP_DETECTED, PipelineStopReason.BUDGET_EXCEEDED):
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
        inserted = await self._owner._write_facts(ctx.memory, ctx.user_message)
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
            )
            return MemoryWriteResult(component_name=self.name, status="degraded", updated_count=1)

        await self._owner._write_summary(
            ctx.memory,
            ctx.user_message,
            ctx.assistant_final,
        )
        return MemoryWriteResult(component_name=self.name, status="ok", updated_count=1)


def _rebuild_raw_tail(
    previous_tail: str,
    user_message: str,
    assistant_final: str,
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
    if len(joined) <= RAW_TAIL_MAX_CHARS:
        return joined
    # Clip from the front — keep the most recent content.
    return joined[-RAW_TAIL_MAX_CHARS:]


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
