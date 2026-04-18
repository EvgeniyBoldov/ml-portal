"""
RuntimePipeline — the single orchestrator of a chat/sandbox turn.

Flow:
    1. Load or create WorkingMemory for this run (or resume a paused one).
    2. Triage → TriageDecision.
    3. Dispatch on intent:
         final      → stream answer, finish.
         clarify    → waiting_input, pause.
         resume     → load paused memory, continue at step 4.
         orchestrate→ continue at step 4.
    4. Preflight for the selected agent (or the planner's default agent container).
    5. Planner loop:
         NextStep decision → dispatch:
             call_agent → AgentExecutor
             ask_user   → pause
             final      → Synthesizer streams final
             abort      → fail
    6. Terminal: persist memory, emit STOP or FINAL + DONE.

This class is the only point that owns OrchestrationPhase envelopes and
event sequence numbers. Everything else yields bare RuntimeEvents.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ToolContext
from app.agents.execution_preflight import ExecutionMode
from app.core.db import get_session_factory
from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.runtime.agent_executor import AgentExecutor
from app.services.run_store import RunStore
from app.runtime.contracts import (
    NextStep,
    NextStepKind,
    PipelineRequest,
    PipelineStopReason,
    TriageDecision,
    TriageIntent,
)
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.memory import WorkingMemoryRepository
from app.runtime.memory.working_memory import (
    AgentResult,
    ChatMessageRef,
    PlannerStepRecord,
    WorkingMemory,
)
from app.runtime.planner import Planner
from app.runtime.synthesizer import Synthesizer
from app.runtime.triage import Triage
from app.services.runtime_config_service import RuntimeConfigService

logger = get_logger(__name__)


MAX_PLANNER_ITERATIONS_DEFAULT = 12
MAX_WALL_TIME_MS_DEFAULT = 120_000


class RuntimePipeline:
    """Single-class orchestrator. No thin wrappers."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        run_store: Optional[RunStore] = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.run_store = run_store

        self.memory_repo = WorkingMemoryRepository(session)
        self.triage = Triage(session=session, llm_client=llm_client)
        self.planner = Planner(session=session, llm_client=llm_client)
        self.agent_executor = AgentExecutor(
            session=session, llm_client=llm_client, run_store=run_store,
        )
        self.synthesizer = Synthesizer(session=session, llm_client=llm_client)
        self.config_service = RuntimeConfigService(session)

    # ------------------------------------------------------------------ #
    # Public entrypoint                                                  #
    # ------------------------------------------------------------------ #

    async def execute(
        self,
        request: PipelineRequest,
        ctx: ToolContext,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        phase = OrchestrationPhase.PIPELINE
        event_seq = 0
        chat_uuid: Optional[UUID] = UUID(request.chat_id) if request.chat_id else None
        user_uuid = UUID(request.user_id)
        tenant_uuid = UUID(request.tenant_id)

        def emit(event: RuntimeEvent, p: OrchestrationPhase, run_id: Optional[str] = None) -> RuntimeEvent:
            nonlocal event_seq
            event_seq += 1
            return event.with_envelope(
                phase=p,
                sequence=event_seq,
                run_id=run_id,
                chat_id=request.chat_id,
            )

        # --- 1. Load latest memory for cross-turn context & paused-run detection.
        # In sandbox mode (chat_id is None) there is no cross-turn context to
        # pull — each run is standalone.
        latest_memory = (
            await self.memory_repo.load_latest_for_chat(chat_uuid) if chat_uuid else None
        )
        paused_runs = (
            await self.memory_repo.load_paused_for_chat(chat_uuid) if chat_uuid else []
        )

        platform_config = await self._load_platform_config()

        # --- 2. Seed a fresh WorkingMemory for this turn.
        run_id = uuid4()
        memory = self._seed_memory(
            run_id=run_id,
            request=request,
            user_id=user_uuid,
            tenant_id=tenant_uuid,
            chat_id=chat_uuid,
            latest=latest_memory,
        )
        await self._persist(memory)

        yield emit(RuntimeEvent.status("pipeline_started", run_id=str(run_id)), phase)

        # --- 3. Triage.
        yield emit(RuntimeEvent.status("triage"), OrchestrationPhase.TRIAGE)
        routable_agents = await self._list_routable_agents()
        triage = await self.triage.decide(
            request_text=request.request_text,
            memory=latest_memory or memory,
            routable_agents=routable_agents,
            paused_runs=paused_runs,
            platform_config=platform_config,
            chat_id=chat_uuid,
            tenant_id=tenant_uuid,
            user_id=user_uuid,
        )
        memory.intent = triage.intent.value
        memory.goal = triage.goal or memory.goal or request.request_text
        await self._persist(memory)
        yield emit(
            RuntimeEvent.status(
                "triage_complete",
                intent=triage.intent.value,
                confidence=triage.confidence,
                reason=triage.reason,
            ),
            OrchestrationPhase.TRIAGE,
        )

        # --- 4. Dispatch on triage intent.
        if triage.intent == TriageIntent.FINAL:
            answer = triage.answer or ""
            yield emit(RuntimeEvent.status("direct_answer"), OrchestrationPhase.TRIAGE)
            for i in range(0, len(answer), 20):
                yield emit(RuntimeEvent.delta(answer[i : i + 20]), OrchestrationPhase.TRIAGE)
            memory.final_answer = answer
            memory.status = PipelineStopReason.COMPLETED.value
            memory.finished_at = datetime.now(timezone.utc)
            await self._persist(memory)
            yield emit(
                RuntimeEvent.final(answer, sources=[], run_id=str(run_id)),
                OrchestrationPhase.TRIAGE,
                run_id=str(run_id),
            )
            return

        if triage.intent == TriageIntent.CLARIFY:
            question = triage.clarify_prompt or "Уточни, пожалуйста, что именно ты хочешь сделать?"
            memory.add_open_question(question)
            memory.status = PipelineStopReason.WAITING_INPUT.value
            await self._persist(memory)
            yield emit(RuntimeEvent.waiting_input(question, run_id=str(run_id)), OrchestrationPhase.TRIAGE)
            yield emit(
                RuntimeEvent.stop(PipelineStopReason.WAITING_INPUT.value, run_id=str(run_id), question=question),
                OrchestrationPhase.TRIAGE,
                run_id=str(run_id),
            )
            return

        if triage.intent == TriageIntent.RESUME and triage.resume_run_id is not None:
            resumed = await self.memory_repo.load(triage.resume_run_id)
            if resumed is not None:
                # Carry forward open questions resolution: assume the user answered one.
                resumed.consume_open_question()
                resumed.status = "running"
                memory = resumed
                run_id = memory.run_id
                await self._persist(memory)
                yield emit(
                    RuntimeEvent.status("resumed_paused_run", run_id=str(run_id)),
                    OrchestrationPhase.TRIAGE,
                )
            # If resume failed we fall through to orchestrate path with fresh memory.

        # --- 5. Orchestrate via planner loop.
        effective_agent_slug = request.agent_slug or triage.agent_hint
        available_agents_for_planner = await self._available_agents_for_planner(
            routable_agents, effective_agent_slug,
        )
        if not available_agents_for_planner:
            yield emit(RuntimeEvent.error("No agents available for orchestration", recoverable=False), OrchestrationPhase.PREFLIGHT, run_id=str(run_id))
            memory.status = PipelineStopReason.FAILED.value
            memory.final_error = "no_agents_available"
            memory.finished_at = datetime.now(timezone.utc)
            await self._persist(memory)
            return

        policy = self._derive_policy_limits(platform_config)
        memory.goal = memory.goal or request.request_text

        async for event in self._planner_loop(
            memory=memory,
            request=request,
            ctx=ctx,
            user_id=user_uuid,
            tenant_id=tenant_uuid,
            run_id=run_id,
            available_agents=available_agents_for_planner,
            platform_config=platform_config,
            policy=policy,
            emit=emit,
        ):
            yield event

    # ------------------------------------------------------------------ #
    # Planner loop                                                       #
    # ------------------------------------------------------------------ #

    async def _planner_loop(
        self,
        *,
        memory: WorkingMemory,
        request: PipelineRequest,
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        run_id: UUID,
        available_agents: List[Dict[str, Any]],
        platform_config: Dict[str, Any],
        policy: Dict[str, int],
        emit,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        max_iters = policy["max_steps"]
        max_wall_time_ms = policy["max_wall_time_ms"]
        chat_uuid = memory.chat_id

        while memory.iter_count < max_iters:
            yield emit(
                RuntimeEvent.status("planner_thinking", iteration=memory.iter_count + 1),
                OrchestrationPhase.PLANNER,
                run_id=str(run_id),
            )

            try:
                step = await self.planner.next_step(
                    memory=memory,
                    available_agents=available_agents,
                    outline=memory.outline,
                    platform_config=platform_config,
                    chat_id=chat_uuid,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_run_id=run_id,
                )
            except Exception as exc:
                logger.error("Planner failure on iter=%s: %s", memory.iter_count, exc, exc_info=True)
                memory.status = PipelineStopReason.FAILED.value
                memory.final_error = f"planner_exception: {exc}"
                memory.finished_at = datetime.now(timezone.utc)
                await self._persist(memory)
                yield emit(
                    RuntimeEvent.error(f"Planner failed: {exc}", recoverable=False),
                    OrchestrationPhase.PLANNER,
                    run_id=str(run_id),
                )
                return

            # Record + stream planner decision.
            step_record = PlannerStepRecord(
                iteration=memory.iter_count + 1,
                kind=step.kind.value,
                agent_slug=step.agent_slug,
                phase_id=step.phase_id,
                rationale=step.rationale,
            )
            memory.add_planner_step(step_record)
            await self._persist(memory)

            yield emit(
                RuntimeEvent.planner_step(
                    iteration=step_record.iteration,
                    kind=step.kind.value,
                    payload={
                        "agent_slug": step.agent_slug,
                        "rationale": step.rationale,
                        "phase_id": step.phase_id,
                        "risk": step.risk,
                    },
                ),
                OrchestrationPhase.PLANNER,
                run_id=str(run_id),
            )

            # Loop detection.
            if memory.detect_loop():
                memory.add_fact(
                    "Loop detected by runtime; synthesizing from facts.",
                    source="pipeline",
                )
                yield emit(
                    RuntimeEvent.status("loop_detected"),
                    OrchestrationPhase.PLANNER,
                    run_id=str(run_id),
                )
                async for ev in self._finalize(
                    memory=memory, run_id=run_id, emit=emit,
                    stop_reason=PipelineStopReason.LOOP_DETECTED,
                    planner_hint=None, model=request.model,
                ):
                    yield ev
                return

            # Dispatch.
            if step.kind == NextStepKind.FINAL:
                async for ev in self._finalize(
                    memory=memory, run_id=run_id, emit=emit,
                    stop_reason=PipelineStopReason.COMPLETED,
                    planner_hint=step.final_answer,
                    model=request.model,
                ):
                    yield ev
                return

            if step.kind == NextStepKind.ASK_USER:
                question = step.question or "Нужны дополнительные данные для продолжения."
                memory.add_open_question(question)
                memory.status = PipelineStopReason.WAITING_INPUT.value
                await self._persist(memory)
                yield emit(
                    RuntimeEvent.waiting_input(question, run_id=str(run_id)),
                    OrchestrationPhase.PLANNER,
                    run_id=str(run_id),
                )
                yield emit(
                    RuntimeEvent.stop(
                        PipelineStopReason.WAITING_INPUT.value,
                        run_id=str(run_id),
                        question=question,
                    ),
                    OrchestrationPhase.PLANNER,
                    run_id=str(run_id),
                )
                return

            if step.kind == NextStepKind.ABORT:
                memory.status = PipelineStopReason.ABORTED.value
                memory.final_error = step.rationale
                memory.finished_at = datetime.now(timezone.utc)
                await self._persist(memory)
                yield emit(
                    RuntimeEvent.error(f"Aborted: {step.rationale}", recoverable=False),
                    OrchestrationPhase.PLANNER,
                    run_id=str(run_id),
                )
                return

            # kind == CALL_AGENT
            async for event in self.agent_executor.execute(
                step=step,
                memory=memory,
                messages=request.messages,
                ctx=ctx,
                user_id=user_id,
                tenant_id=tenant_id,
                platform_config=platform_config,
                sandbox_overrides=request.sandbox_overrides,
                model=request.model,
            ):
                yield emit(event, OrchestrationPhase.AGENT, run_id=str(run_id))

            await self._persist(memory)

            # Budget: wall time is approximated via iteration count for now.
            # TODO: track elapsed ms when adding deadlines.
            _ = max_wall_time_ms  # reserved for future deadline checks

        # Max iterations reached.
        yield emit(
            RuntimeEvent.status("max_iters_reached", iterations=memory.iter_count),
            OrchestrationPhase.PLANNER,
            run_id=str(run_id),
        )
        async for ev in self._finalize(
            memory=memory, run_id=run_id, emit=emit,
            stop_reason=PipelineStopReason.MAX_ITERS,
            planner_hint=None, model=request.model,
        ):
            yield ev

    # ------------------------------------------------------------------ #
    # Finalization                                                       #
    # ------------------------------------------------------------------ #

    async def _finalize(
        self,
        *,
        memory: WorkingMemory,
        run_id: UUID,
        emit,
        stop_reason: PipelineStopReason,
        planner_hint: Optional[str],
        model: Optional[str],
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Run synthesizer, persist final state, emit FINAL envelope."""
        async for event in self.synthesizer.stream(
            memory=memory,
            run_id=run_id,
            model=model,
            planner_hint=planner_hint,
        ):
            yield emit(event, OrchestrationPhase.SYNTHESIS, run_id=str(run_id))

        memory.status = stop_reason.value
        memory.finished_at = datetime.now(timezone.utc)
        await self._persist(memory)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _seed_memory(
        self,
        *,
        run_id: UUID,
        request: PipelineRequest,
        user_id: UUID,
        tenant_id: UUID,
        chat_id: Optional[UUID],
        latest: Optional[WorkingMemory],
    ) -> WorkingMemory:
        memory = WorkingMemory(
            run_id=run_id,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            goal=request.request_text,
            question=request.request_text,
            status="running",
        )
        if latest is not None:
            memory.dialogue_summary = latest.dialogue_summary
            memory.recent_messages = list(latest.recent_messages)
        # Derive a lightweight recent_messages snapshot from current messages.
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

    async def _persist(self, memory: WorkingMemory) -> None:
        try:
            await self.memory_repo.save(memory)
        except Exception as exc:
            logger.warning("Failed to persist WorkingMemory run=%s: %s", memory.run_id, exc)

    async def _load_platform_config(self) -> Dict[str, Any]:
        try:
            return await self.config_service.get_pipeline_config()
        except Exception as exc:
            logger.warning("Failed to load platform config, using empty: %s", exc)
            return {}

    async def _list_routable_agents(self) -> List[Dict[str, Any]]:
        from app.services.agent_service import AgentService

        try:
            svc = AgentService(self.session)
            agents = await svc.list_routable_agents()
            return [
                {
                    "slug": getattr(a, "slug", None),
                    "description": getattr(a, "description", "") or "",
                }
                for a in agents
                if getattr(a, "slug", None)
            ]
        except Exception as exc:
            logger.warning("Failed to list routable agents: %s", exc)
            return []

    async def _available_agents_for_planner(
        self,
        routable_agents: List[Dict[str, Any]],
        explicit_slug: Optional[str],
    ) -> List[Dict[str, Any]]:
        if explicit_slug:
            # Pin planner to the explicit agent by presenting only that one.
            return [{"slug": explicit_slug, "description": ""}]
        return routable_agents

    @staticmethod
    def _derive_policy_limits(platform_config: Dict[str, Any]) -> Dict[str, int]:
        policy = platform_config.get("policy") if isinstance(platform_config, dict) else None
        policy = policy or {}
        return {
            "max_steps": int(policy.get("max_steps") or MAX_PLANNER_ITERATIONS_DEFAULT),
            "max_wall_time_ms": int(policy.get("max_wall_time_ms") or MAX_WALL_TIME_MS_DEFAULT),
        }
