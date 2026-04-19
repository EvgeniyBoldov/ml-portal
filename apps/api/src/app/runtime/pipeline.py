"""
RuntimePipeline — thin coordinator (post-M5: no triage).

Responsibilities (and NOTHING else):
    1. Resolve tenant/user/chat ids from the incoming request.
    2. Load the platform snapshot (config + routable agents + policy).
    3. Ask `MemoryBuilder` to assemble the turn's memory from the
       persisted FactStore + SummaryStore (and seed a legacy WorkingMemory
       object from it — the legacy WM stays as runtime-state carrier
       until M6).
    4. Run the PlanningStage — single decision engine:
           DIRECT_ANSWER → planner streamed answer, outcome=DIRECT
           CLARIFY/ASK_USER → pause (waiting_input)
           CALL_AGENT loop → eventually FINAL / ABORT / max_iters
    5. Run FinalizationStage for NEEDS_FINAL outcomes (synthesizer).
    6. Hand off to `MemoryWriter.finalize` to persist extracted facts
       and the updated DialogueSummary for next-turn memory.

Triage is gone. The planner absorbs direct_answer + clarify. The
rolling summary job is delegated to MemoryWriter + SummaryCompactor.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.assembler import PipelineAssembler
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import EventEnvelopeStamper
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.memory.fact_extractor import AgentResultSnippet
from app.runtime.memory.transport import TurnMemory
from app.runtime.memory.working_memory import Fact as LegacyFact
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.platform_config import PlatformConfigLoader
from app.runtime.stages.planning_stage import PlanningOutcomeKind
from app.services.run_store import RunStore

logger = get_logger(__name__)


class RuntimePipeline:
    """Coordinator. Stateless between turns; all turn state lives in
    per-turn state objects built by the assembler."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self._session = session
        self._assembler = PipelineAssembler(
            session=session, llm_client=llm_client, run_store=run_store,
        )

    # ------------------------------------------------------------------ #
    # Public entrypoint                                                  #
    # ------------------------------------------------------------------ #

    async def execute(
        self,
        request: PipelineRequest,
        ctx: ToolContext,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        chat_id: Optional[UUID] = UUID(request.chat_id) if request.chat_id else None
        user_id = UUID(request.user_id)
        tenant_id = UUID(request.tenant_id)

        envelope = EventEnvelopeStamper(chat_id=request.chat_id)
        platform = await PlatformConfigLoader(self._session).load()

        # --- Memory: read path (new) ------------------------------------
        # MemoryBuilder pulls facts + structured summary from the new
        # persistence layer (FactStore / SummaryStore). We then seed a
        # legacy WorkingMemory from it so existing planner/stages, which
        # still speak that shape, keep working. When the legacy WM class
        # is retired in M6, this adapter disappears entirely.
        turn_mem = await self._assembler.memory_builder.build(
            goal=request.request_text,
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        memory = self._seed_legacy_from_turn_memory(
            turn_mem=turn_mem,
            request=request,
            user_id=user_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
        )

        # --- Planning (single decision engine) --------------------------
        explicit_slug = request.agent_slug
        available_agents = platform.available_agents_for_planner(explicit_slug)

        planning_stage = self._assembler.build_planning_stage(
            max_iterations=platform.policy.max_steps,
            max_wall_time_ms=platform.policy.max_wall_time_ms,
        )
        async for phased in planning_stage.run(
            memory=memory,
            request=request,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            available_agents=available_agents,
            platform_config=platform.config,
        ):
            yield envelope.stamp_phased(phased, run_id=str(memory.run_id))

        assert planning_stage.outcome is not None
        planning_outcome = planning_stage.outcome

        if planning_outcome.kind in (
            PlanningOutcomeKind.PAUSED,
            PlanningOutcomeKind.ABORTED,
            PlanningOutcomeKind.FAILED,
        ):
            # Memory write-back still runs for paused/aborted turns so
            # next turn sees the open_questions / error context.
            await self._finalize_memory(
                turn_mem=turn_mem,
                legacy_memory=memory,
                request=request,
            )
            return

        # --- Finalization -----------------------------------------------
        if planning_outcome.kind == PlanningOutcomeKind.NEEDS_FINAL:
            async for ev in self._run_finalization(
                memory=memory,
                stop_reason=planning_outcome.stop_reason,
                planner_hint=planning_outcome.planner_hint,
                model=request.model,
                envelope=envelope,
            ):
                yield ev
        # PlanningOutcomeKind.DIRECT already emitted delta+final inside
        # the stage; nothing to finalize beyond memory write-back below.

        # --- Memory: write path (new) -----------------------------------
        await self._finalize_memory(
            turn_mem=turn_mem,
            legacy_memory=memory,
            request=request,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _run_finalization(
        self,
        *,
        memory,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        model: Optional[str],
        envelope: EventEnvelopeStamper,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        final_stage = self._assembler.build_finalization_stage()
        async for phased in final_stage.run(
            memory=memory,
            stop_reason=stop_reason,
            planner_hint=planner_hint,
            model=model,
            run_synthesizer=True,
        ):
            yield envelope.stamp_phased(phased, run_id=str(memory.run_id))

    async def _finalize_memory(
        self,
        *,
        turn_mem: TurnMemory,
        legacy_memory: WorkingMemory,
        request: PipelineRequest,
    ) -> None:
        """Persist the turn's memory effects via MemoryWriter.

        Wraps every call in best-effort error handling: a write failure
        must never surface to the caller — the user already got their
        answer, we'd rather miss one turn of memory than double-fault.
        """
        # Bridge agent_results from legacy WM (pydantic) into AgentResultSnippet
        # (pydantic BaseModel with the shape FactExtractor + SummaryCompactor expect).
        turn_mem.agent_results = [
            AgentResultSnippet(
                agent=ar.agent_slug,
                summary=ar.summary,
                success=ar.success,
            )
            for ar in legacy_memory.agent_results
        ]
        try:
            await self._assembler.memory_writer.finalize(
                memory=turn_mem,
                user_message=request.request_text,
                assistant_final=legacy_memory.final_answer or "",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MemoryWriter.finalize best-effort failed: %s", exc)

    # ---------------------------------------------------- legacy-bridge --

    @staticmethod
    def _seed_legacy_from_turn_memory(
        *,
        turn_mem: TurnMemory,
        request: PipelineRequest,
        user_id: UUID,
        tenant_id: UUID,
        chat_id: Optional[UUID],
    ) -> WorkingMemory:
        """Construct a legacy `WorkingMemory` from the new `TurnMemory`.

        This is the only place where the two memory shapes meet. Once
        the legacy WorkingMemory is retired (M6), the pipeline will
        consume `TurnMemory` directly.

        What we carry over:
          * dialogue_summary — flattened from the structured SummaryDTO
            (goals + open_questions + raw_tail), sized for small-context
            local models.
          * facts — lifted from `retrieved_facts` as legacy Fact objects.
            The legacy planner reads these as atomic evidence strings.
          * recent_messages — last few items from request.messages.
        """
        from uuid import uuid4  # local import: keeps module import cheap
        from app.runtime.memory.working_memory import ChatMessageRef

        memory = WorkingMemory(
            run_id=uuid4(),
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            goal=request.request_text,
            question=request.request_text,
            status="running",
        )

        memory.dialogue_summary = _flatten_summary(turn_mem) or None

        for f in turn_mem.retrieved_facts:
            memory.add_fact(
                text=f"{f.subject}: {f.value}",
                source=f.source.value,
            )

        refs: List[ChatMessageRef] = []
        for m in request.messages[-10:]:
            refs.append(
                ChatMessageRef(
                    message_id=str(m.get("message_id") or m.get("id") or ""),
                    role=str(m.get("role") or "user"),
                    preview=str(m.get("content") or "")[:200],
                )
            )
        memory.set_recent_messages(refs)
        return memory


def _flatten_summary(turn_mem: TurnMemory) -> str:
    """Render the structured SummaryDTO into a compact prose blob for
    consumers that still expect a `dialogue_summary` string (legacy
    planner + synthesizer). Deterministic, short, cheap."""
    s = turn_mem.summary
    parts: List[str] = []
    if s.goals:
        parts.append("Открытые цели: " + "; ".join(s.goals))
    if s.done:
        parts.append("Уже сделано: " + "; ".join(s.done))
    if s.open_questions:
        parts.append("Незакрытые вопросы: " + "; ".join(s.open_questions))
    if s.entities:
        parts.append(
            "Сущности: " + "; ".join(f"{k}={v}" for k, v in s.entities.items())
        )
    if s.raw_tail:
        parts.append("Последние реплики:\n" + s.raw_tail)
    return "\n".join(parts)
