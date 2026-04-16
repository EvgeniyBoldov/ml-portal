"""
PlannerRuntime — next-step orchestrator.

Planner NEVER calls tools directly. It decides which agent to call next
based on goal + execution outline hints + accumulated facts.
Each agent is autonomous — it uses AgentToolRuntime with its own tool loop.

Flow per iteration:
1. Planner LLM: goal + outline + facts → NextAction (agent_call | final | ask_user)
2. If agent_call → route target agent → AgentToolRuntime.execute() → collect fact
3. If final → LLM synthesis from accumulated facts → stream answer → done
4. If ask_user → pause → done
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.contracts import ActionType, ExecutionOutline, HelperSummary, OutlineProgress
from app.agents.runtime.base import BaseRuntime
from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.agents.runtime.sub_agent_dispatcher import SubAgentDispatcher
from app.schemas.system_llm_roles import PlannerInput
from app.services.execution_memory_service import ExecutionMemoryService
from app.services.system_llm_executor import SystemLLMExecutor
from app.core.logging import get_logger
from app.core.db import get_session_factory

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)


class PlannerRuntime(BaseRuntime):
    """Sequential planner that orchestrates agents, not tools."""

    @staticmethod
    def _load_helper_summary(ctx: "ToolContext") -> HelperSummary:
        raw = ctx.get_runtime_deps().helper_summary or {}
        if isinstance(raw, HelperSummary):
            return raw
        if isinstance(raw, dict):
            return HelperSummary.model_validate(raw)
        return HelperSummary()

    @staticmethod
    def _load_execution_outline(ctx: "ToolContext", fallback_goal: str) -> ExecutionOutline:
        raw = ctx.get_runtime_deps().execution_outline or {}
        if isinstance(raw, ExecutionOutline):
            return raw
        if isinstance(raw, dict) and raw:
            return ExecutionOutline.model_validate(raw)
        return ExecutionOutline(
            goal=fallback_goal,
            phases=[],
        )

    @staticmethod
    def _current_phase(outline: ExecutionOutline, progress: OutlineProgress) -> Optional[Any]:
        for phase in outline.phases:
            if phase.phase_id not in progress.completed_phase_ids:
                return phase
        return outline.phases[-1] if outline.phases else None

    @staticmethod
    def _can_finalize(outline: ExecutionOutline, progress: OutlineProgress) -> bool:
        for phase in outline.phases:
            if phase.must_do and not phase.allow_final_after and phase.phase_id not in progress.completed_phase_ids:
                return False
        return True

    @staticmethod
    def _update_phase_progress(
        progress: OutlineProgress,
        outline: ExecutionOutline,
        next_action: Any,
        observation_summary: Optional[str] = None,
        *,
        mark_completed: bool = True,
    ) -> None:
        phase_id = next_action.meta.phase_id if next_action.meta and next_action.meta.phase_id else progress.current_phase_id
        phase = next((item for item in outline.phases if item.phase_id == phase_id), None)
        if not phase:
            phase = PlannerRuntime._current_phase(outline, progress)
            if not phase:
                return
            phase_id = phase.phase_id

        progress.current_phase_id = phase_id
        note = observation_summary or (next_action.meta.why if next_action.meta and next_action.meta.why else None)
        if note:
            progress.add_phase_note(phase_id, note[:300])

        if next_action.type == ActionType.ASK_USER or not mark_completed:
            return

        if phase.phase_id == "finalize":
            return

        progress.mark_phase_completed(phase_id)
        next_phase = PlannerRuntime._current_phase(outline, progress)
        progress.current_phase_id = next_phase.phase_id if next_phase else phase_id

    @staticmethod
    def _resolve_session_factory(ctx: "ToolContext") -> Any:
        deps = ctx.get_runtime_deps()
        return deps.session_factory or get_session_factory()

    async def execute(
        self,
        exec_request: ExecutionRequest,
        messages: List[Dict[str, Any]],
        ctx: ToolContext,
        model: Optional[str] = None,
        enable_logging: bool = True,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        from app.agents.contracts import (
            ActionType,
            Observation,
            ObservationError,
            ObservationStatus,
            PolicyDecisionType,
            StopReason,
        )
        from app.agents.planner import validate_next_action
        from app.agents.policy_engine import PolicyEngine
        from app.agents.run_context_compact import RunContextCompact

        agent = exec_request.agent
        available_actions = exec_request.available_actions
        helper_summary = self._load_helper_summary(ctx)

        if not available_actions:
            logger.error("No available_actions in exec_request, cannot proceed")
            yield RuntimeEvent.error("No available actions configured", recoverable=False)
            return

        session_factory = self._resolve_session_factory(ctx)
        if not session_factory:
            raise ValueError("No DB session factory for planner runtime")

        policy, gen, platform_config = await self.config_resolver.resolve(
            exec_request, ctx, model,
        )

        policy_engine = PolicyEngine.from_platform_config(
            platform_config, max_iters=policy.max_steps,
        )
        resolved_logging_level = await self.logging_resolver.resolve_logging_level(
            ctx,
            getattr(agent, "logging_level", None),
        )

        run_session = self._create_run_session(
            ctx=ctx,
            agent_slug=agent.slug,
            mode="sequential_planner",
            logging_level=resolved_logging_level.value,
            context_snapshot={
                "available_agents": [a.agent_slug for a in available_actions.agents],
            },
            enable_logging=enable_logging,
        )
        await run_session.start()

        async with session_factory() as planner_session:
            memory_service = ExecutionMemoryService(planner_session)
            system_executor = SystemLLMExecutor(
                session=planner_session, llm_client=self.llm.raw_client,
            )

            # Compact context for planner
            user_content = messages[-1].get("content", "") if messages else ""
            compact_ctx = RunContextCompact(goal=user_content)
            execution_outline = self._load_execution_outline(ctx, user_content)
            outline_progress = OutlineProgress()
            first_phase = self._current_phase(execution_outline, outline_progress)
            outline_progress.current_phase_id = first_phase.phase_id if first_phase else None

            conversation_summary = self._build_conversation_summary(messages)
            await memory_service.get_or_create(
                run_id=exec_request.run_id,
                chat_id=getattr(ctx, "chat_id", None),
                tenant_id=getattr(ctx, "tenant_id", None),
                goal=user_content,
                question=user_content,
                dialogue_summary=conversation_summary,
            )
            await memory_service.update_context(
                exec_request.run_id,
                chat_id=getattr(ctx, "chat_id", None),
                tenant_id=getattr(ctx, "tenant_id", None),
                current_phase_id=outline_progress.current_phase_id,
                state={
                    "helper_summary": helper_summary.model_dump(),
                    "execution_outline": execution_outline.model_dump(),
                },
            )

            await run_session.log_step("user_request", {
                "content": user_content, "agent_slug": agent.slug,
                "mode": "sequential_planner",
            })

            budget_payload = {
                "max_steps": policy.max_steps,
                "max_tool_calls_total": policy.max_tool_calls_total,
                "max_wall_time_ms": policy.max_wall_time_ms,
                "tool_timeout_ms": policy.tool_timeout_ms,
                "max_retries": policy.max_retries,
            }
            await run_session.log_step("budget_policy", budget_payload)
            yield RuntimeEvent(RuntimeEventType.STATUS, {
                "stage": "budget_policy",
                "policy": budget_payload,
            })

            yield RuntimeEvent(RuntimeEventType.STATUS, {
                "stage": "planner_outline_loaded",
                "current_phase_id": outline_progress.current_phase_id,
                "completed_phase_ids": list(outline_progress.completed_phase_ids),
            })

            yield RuntimeEvent.status("planner_loop_started")
            start_time = time.time()

            try:
                for iteration in range(policy.max_steps):
                    elapsed_ms = (time.time() - start_time) * 1000
                    if elapsed_ms > policy.max_wall_time_ms:
                        yield RuntimeEvent.error("Wall time limit exceeded", recoverable=False)
                        await memory_service.finish_run(
                            exec_request.run_id,
                            status="failed",
                            final_error="Wall time limit exceeded",
                            chat_id=getattr(ctx, "chat_id", None),
                            tenant_id=getattr(ctx, "tenant_id", None),
                        )
                        await run_session.finish("failed", "Wall time limit exceeded")
                        return

                    yield RuntimeEvent.thinking(iteration + 1)

                    # 1. Planner decides next action
                    planner_start = time.time()

                    session_state = {}
                    if compact_ctx.facts:
                        session_state["previous_observations"] = list(compact_ctx.facts)
                        session_state["iteration"] = iteration + 1
                    if helper_summary.facts:
                        session_state["summary_facts"] = list(helper_summary.facts)
                    session_state["outline_progress"] = outline_progress.model_dump()
                    session_state["execution_memory"] = await memory_service.snapshot(exec_request.run_id)

                    planner_input = PlannerInput(
                        goal=compact_ctx.goal,
                        conversation_summary=conversation_summary,
                        session_state=session_state,
                        available_agents=[{
                            "slug": a.agent_slug,
                            "description": a.description or "",
                        } for a in available_actions.agents],
                        available_operations=[],  # Planner does NOT execute operations directly
                        policies=platform_config.get("policies_text") or "default",
                        execution_outline=execution_outline.model_dump(),
                    )

                    next_action = await system_executor.execute_planner_with_fallback(planner_input)
                    planner_duration = int((time.time() - planner_start) * 1000)

                    validation_error = validate_next_action(next_action, available_actions)
                    if validation_error:
                        logger.warning("Planner returned invalid next action: %s", validation_error)
                        if (
                            next_action.type == ActionType.AGENT_CALL
                            and next_action.agent is not None
                            and len(available_actions.agents) == 1
                        ):
                            next_action.agent.agent_slug = available_actions.agents[0].agent_slug
                            if next_action.meta:
                                next_action.meta.why = (
                                    f"{next_action.meta.why or 'Planner selected unavailable agent'}; "
                                    f"forced to allowed agent '{next_action.agent.agent_slug}'"
                                )
                        else:
                            raise ValueError(f"Planner produced invalid next action: {validation_error}")

                    if next_action.meta and not next_action.meta.phase_id and outline_progress.current_phase_id:
                        current_phase = self._current_phase(execution_outline, outline_progress)
                        next_action.meta.phase_id = outline_progress.current_phase_id
                        next_action.meta.phase_title = current_phase.title if current_phase else None

                    await run_session.log_step("planner_action", {
                        "iteration": iteration + 1,
                        "action_type": next_action.type.value,
                        "agent_slug": next_action.agent.agent_slug if next_action.agent else None,
                        "why": next_action.meta.why if next_action.meta else None,
                        "phase_id": next_action.meta.phase_id if next_action.meta else None,
                    }, duration_ms=planner_duration)

                    await memory_service.record_step(
                        exec_request.run_id,
                        step_type="planner_action",
                        payload={
                            "iteration": iteration + 1,
                            "action_type": next_action.type.value,
                            "agent_slug": next_action.agent.agent_slug if next_action.agent else None,
                            "why": next_action.meta.why if next_action.meta else None,
                            "phase_id": next_action.meta.phase_id if next_action.meta else None,
                            "phase_title": next_action.meta.phase_title if next_action.meta else None,
                        },
                        signature=(
                            f"{next_action.type.value}:"
                            f"{next_action.agent.agent_slug if next_action.agent else 'none'}:"
                            f"{next_action.meta.phase_id if next_action.meta and next_action.meta.phase_id else outline_progress.current_phase_id or 'none'}"
                        ),
                        chat_id=getattr(ctx, "chat_id", None),
                        tenant_id=getattr(ctx, "tenant_id", None),
                        current_phase_id=next_action.meta.phase_id if next_action.meta and next_action.meta.phase_id else outline_progress.current_phase_id,
                        current_agent_slug=next_action.agent.agent_slug if next_action.agent else None,
                    )

                    yield RuntimeEvent(RuntimeEventType.PLANNER_ACTION, {
                        "iteration": iteration + 1,
                        "action_type": next_action.type.value,
                        "agent_slug": next_action.agent.agent_slug if next_action.agent else None,
                        "phase_id": next_action.meta.phase_id if next_action.meta else None,
                        "phase_title": next_action.meta.phase_title if next_action.meta else None,
                    })

                    previous_tail = list(compact_ctx.recent_signatures)[-2:]
                    compact_ctx.record_action(next_action)

                    if compact_ctx.is_looping():
                        repeated_target = (
                            next_action.agent.agent_slug
                            if next_action.type == ActionType.AGENT_CALL and next_action.agent
                            else next_action.type.value
                        )
                        logger.warning(
                            "Planner loop detected: repeated action '%s' at iteration %s",
                            repeated_target,
                            iteration + 1,
                        )
                        await run_session.log_step("loop_detected", {
                            "iteration": iteration + 1,
                            "action_type": next_action.type.value,
                            "agent_slug": next_action.agent.agent_slug if next_action.agent else None,
                            "recent_signatures": previous_tail + [list(compact_ctx.recent_signatures)[-1]],
                            "facts_collected": len(compact_ctx.facts),
                        })
                        compact_ctx.add_fact(
                            f"[planner] Loop detected on repeated action '{repeated_target}'. "
                            "Stop delegating further and synthesize answer from collected facts."
                        )
                        async for ev in self._synthesize_from_facts(
                            messages, compact_ctx, gen, policy, run_session,
                            memory_service, exec_request, ctx,
                        ):
                            yield ev
                        return

                    # 2. Policy evaluation
                    decision = policy_engine.evaluate(next_action, compact_ctx, available_actions)

                    await run_session.log_step("policy_decision", {
                        "decision": decision.decision.value,
                        "reason": decision.reason,
                        "iteration": iteration + 1,
                    })

                    if decision.decision == PolicyDecisionType.BLOCK:
                        yield RuntimeEvent.error(f"Blocked: {decision.reason}", recoverable=False)
                        await memory_service.finish_run(
                            exec_request.run_id,
                            status="failed",
                            final_error=decision.reason,
                            chat_id=getattr(ctx, "chat_id", None),
                            tenant_id=getattr(ctx, "tenant_id", None),
                        )
                        await run_session.finish("failed", decision.reason)
                        return

                    if decision.decision in (
                        PolicyDecisionType.REQUIRE_CONFIRMATION,
                        PolicyDecisionType.REQUIRE_INPUT,
                    ):
                        reason_val = (
                            StopReason.WAITING_CONFIRMATION
                            if decision.decision == PolicyDecisionType.REQUIRE_CONFIRMATION
                            else StopReason.WAITING_INPUT
                        )
                        yield RuntimeEvent(RuntimeEventType.STOP, {
                            "reason": reason_val.value,
                            "message": decision.reason,
                            "run_id": str(exec_request.run_id),
                        })
                        await memory_service.finish_run(
                            exec_request.run_id,
                            status=reason_val.value,
                            final_error=decision.reason,
                            chat_id=getattr(ctx, "chat_id", None),
                            tenant_id=getattr(ctx, "tenant_id", None),
                        )
                        await run_session.finish(reason_val.value)
                        return

                    # 3. Handle action type
                    if next_action.type == ActionType.FINAL:
                        if not self._can_finalize(execution_outline, outline_progress):
                            current_phase = self._current_phase(execution_outline, outline_progress)
                            blocked_phase = current_phase.phase_id if current_phase else "unknown"
                            compact_ctx.add_fact(f"[planner] FINAL rejected until phase '{blocked_phase}' is complete")
                            await memory_service.add_fact(
                                exec_request.run_id,
                                f"[planner] FINAL rejected until phase '{blocked_phase}' is complete",
                                chat_id=getattr(ctx, "chat_id", None),
                                tenant_id=getattr(ctx, "tenant_id", None),
                            )
                            yield RuntimeEvent(RuntimeEventType.STATUS, {
                                "stage": "final_blocked",
                                "blocked_phase_id": blocked_phase,
                                "completed_phase_ids": list(outline_progress.completed_phase_ids),
                            })
                            continue

                        self._update_phase_progress(
                            outline_progress,
                            execution_outline,
                            next_action,
                            observation_summary="Final answer emitted",
                        )
                        async for ev in self._synthesize_from_facts(
                            messages, compact_ctx, gen, policy, run_session,
                            memory_service, exec_request, ctx,
                        ):
                            yield ev
                        return

                    if next_action.type == ActionType.ASK_USER:
                        question = next_action.ask_user.question if next_action.ask_user else ""
                        self._update_phase_progress(
                            outline_progress,
                            execution_outline,
                            next_action,
                            observation_summary=f"Need user input: {question}",
                        )
                        await memory_service.add_open_question(
                            exec_request.run_id,
                            question,
                            chat_id=getattr(ctx, "chat_id", None),
                            tenant_id=getattr(ctx, "tenant_id", None),
                        )
                        yield RuntimeEvent(RuntimeEventType.WAITING_INPUT, {"question": question})
                        yield RuntimeEvent(RuntimeEventType.STOP, {
                            "reason": StopReason.WAITING_INPUT.value,
                            "question": question,
                            "run_id": str(exec_request.run_id),
                        })
                        await memory_service.finish_run(
                            exec_request.run_id,
                            status="waiting_input",
                            final_error=question or "waiting_input",
                            chat_id=getattr(ctx, "chat_id", None),
                            tenant_id=getattr(ctx, "tenant_id", None),
                        )
                        await run_session.finish("waiting_input")
                        return

                    if next_action.type == ActionType.AGENT_CALL and next_action.agent:
                        dispatcher = SubAgentDispatcher(
                            llm_client=self.llm.raw_client,
                            run_store=self.run_store,
                            update_phase_progress=self._update_phase_progress,
                        )
                        async for ev in dispatcher.dispatch(
                            next_action, exec_request, messages, ctx, model,
                            compact_ctx, run_session, iteration, execution_outline, outline_progress,
                            platform_config, ctx.get_runtime_deps().sandbox_overrides or {}, memory_service, planner_session,
                        ):
                            yield ev
                        continue

                    if next_action.type == ActionType.OPERATION_CALL:
                        logger.warning(
                            "Planner returned OPERATION_CALL — this is unexpected. "
                            "Converting to agent_call for the current agent.",
                        )
                        obs = Observation(
                            status=ObservationStatus.ERROR,
                            summary="Planner should call agents, not operations directly. Retrying.",
                        )
                        compact_ctx.update_from_observation(obs, "planner", "operation_call_rejected")
                        await memory_service.record_step(
                            exec_request.run_id,
                            step_type="planner_reject_operation_call",
                            payload={
                                "iteration": iteration + 1,
                                "summary": obs.summary,
                            },
                            chat_id=getattr(ctx, "chat_id", None),
                            tenant_id=getattr(ctx, "tenant_id", None),
                            current_phase_id=outline_progress.current_phase_id,
                            current_agent_slug="planner",
                        )
                        continue

                async for ev in self._synthesize_from_facts(
                    messages, compact_ctx, gen, policy, run_session,
                    memory_service, exec_request, ctx,
                ):
                    yield ev

            except asyncio.TimeoutError as e:
                logger.warning("Planner timed out after %sms: %s", policy.max_wall_time_ms, e)
                async for ev in self._recover_or_fail(
                    messages=messages,
                    compact_ctx=compact_ctx,
                    gen=gen,
                    policy=policy,
                    run_session=run_session,
                    memory_service=memory_service,
                    exec_request=exec_request,
                    ctx=ctx,
                    error_type="timeout",
                    finish_error="timeout",
                    client_message="Request timed out",
                    recoverable=True,
                ):
                    yield ev

            except (ConnectionError, OSError) as e:
                logger.error("Planner network error: %s", e, exc_info=True)
                async for ev in self._recover_or_fail(
                    messages=messages,
                    compact_ctx=compact_ctx,
                    gen=gen,
                    policy=policy,
                    run_session=run_session,
                    memory_service=memory_service,
                    exec_request=exec_request,
                    ctx=ctx,
                    error_type="network",
                    finish_error=str(e),
                    client_message=f"Connection error: {e}",
                    recoverable=True,
                ):
                    yield ev

            except Exception as e:
                logger.error("Sequential planner failed: %s", e, exc_info=True)
                async for ev in self._recover_or_fail(
                    messages=messages,
                    compact_ctx=compact_ctx,
                    gen=gen,
                    policy=policy,
                    run_session=run_session,
                    memory_service=memory_service,
                    exec_request=exec_request,
                    ctx=ctx,
                    error_type="unexpected",
                    finish_error=str(e),
                    client_message=str(e),
                    recoverable=False,
                ):
                    yield ev
            finally:
                try:
                    await planner_session.commit()
                except Exception:
                    await planner_session.rollback()


    async def _synthesize_from_facts(
        self,
        messages: List[Dict[str, Any]],
        compact_ctx: Any,
        gen: Any,
        policy: Any,
        run_session: Any,
        memory_service: ExecutionMemoryService,
        exec_request: ExecutionRequest,
        ctx: ToolContext,
        *,
        finish_status: str = "completed",
        finish_error: Optional[str] = None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Synthesize final answer from collected planner facts."""
        if compact_ctx.facts:
            facts_text = "\n".join(compact_ctx.facts)
            yield RuntimeEvent.status("generating_answer")

            synthesis_messages = self.prompts.build_planner_synthesis_messages(
                list(messages), facts_text,
            )

            answer_parts: List[str] = []
            async for chunk in self.llm.stream(
                messages=synthesis_messages, model=gen.model,
                temperature=gen.temperature, max_tokens=gen.max_tokens,
            ):
                answer_parts.append(chunk)
                yield RuntimeEvent.delta(chunk)

            final_answer = "".join(answer_parts)
            await memory_service.finish_run(
                exec_request.run_id,
                status=finish_status,
                final_answer=final_answer,
                final_error=finish_error,
                chat_id=getattr(ctx, "chat_id", None),
                tenant_id=getattr(ctx, "tenant_id", None),
            )
            yield RuntimeEvent.final(final_answer, [], run_id=str(exec_request.run_id))
            await run_session.finish(finish_status)
        else:
            error_message = f"Maximum planner iterations ({policy.max_steps}) reached"
            yield RuntimeEvent.error(
                error_message,
                recoverable=True,
            )
            await memory_service.finish_run(
                exec_request.run_id,
                status="failed",
                final_error=f"Max iterations ({policy.max_steps}) reached",
                chat_id=getattr(ctx, "chat_id", None),
                tenant_id=getattr(ctx, "tenant_id", None),
            )
            await run_session.finish(
                "failed", f"Max iterations ({policy.max_steps}) reached",
            )

    async def _recover_or_fail(
        self,
        *,
        messages: List[Dict[str, Any]],
        compact_ctx: Any,
        gen: Any,
        policy: Any,
        run_session: Any,
        memory_service: ExecutionMemoryService,
        exec_request: ExecutionRequest,
        ctx: ToolContext,
        error_type: str,
        finish_error: str,
        client_message: str,
        recoverable: bool,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        await run_session.log_step(
            "error",
            {
                "type": error_type,
                "message": finish_error,
                "facts_collected": len(compact_ctx.facts),
            },
        )
        if compact_ctx.facts:
            logger.info(
                "Planner error '%s' but %s facts collected — attempting synthesis",
                error_type,
                len(compact_ctx.facts),
            )
            async for ev in self._synthesize_from_facts(
                messages,
                compact_ctx,
                gen,
                policy,
                run_session,
                memory_service,
                exec_request,
                ctx,
                finish_status="failed",
                finish_error=finish_error,
            ):
                yield ev
            return

        yield RuntimeEvent.error(client_message, recoverable=recoverable)
        await memory_service.finish_run(
            exec_request.run_id,
            status="failed",
            final_error=finish_error,
            chat_id=getattr(ctx, "chat_id", None),
            tenant_id=getattr(ctx, "tenant_id", None),
        )
        await run_session.finish("failed", finish_error)
