"""
SubAgentDispatcher — executes a single AGENT_CALL action inside the planner loop.

Extracted from PlannerRuntime._handle_agent_call to keep planner.py focused on
orchestration logic, not sub-agent execution mechanics.
"""
from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, TYPE_CHECKING

from app.agents.contracts import ExecutionOutline, OutlineProgress
from app.agents.runtime.events import RuntimeEvent, RuntimeEventType
from app.services.execution_memory_service import ExecutionMemoryService
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)


class SubAgentDispatcher:
    """
    Routes a single AGENT_CALL to the target sub-agent and yields RuntimeEvents.

    Dependencies are passed explicitly to avoid coupling with PlannerRuntime internals.
    """

    def __init__(
        self,
        *,
        llm_client: Any,
        run_store: Any,
        update_phase_progress: Callable[..., None],
    ) -> None:
        self._llm_client = llm_client
        self._run_store = run_store
        self._update_phase_progress = update_phase_progress

    async def dispatch(
        self,
        next_action: Any,
        exec_request: "ExecutionRequest",
        messages: List[Dict[str, Any]],
        ctx: "ToolContext",
        model: Optional[str],
        compact_ctx: Any,
        run_session: Any,
        iteration: int,
        execution_outline: ExecutionOutline,
        outline_progress: OutlineProgress,
        platform_config: Dict[str, Any],
        sandbox_overrides: Dict[str, Any],
        memory_service: ExecutionMemoryService,
        planner_session: Any,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        """Execute AGENT_CALL: prepare sub-agent, run it, record observation."""
        from app.agents.contracts import (
            Observation,
            ObservationError,
            ObservationStatus,
        )

        target_slug = next_action.agent.agent_slug
        yield RuntimeEvent.status(f"delegating_to_{target_slug}")

        try:
            from app.agents.execution_preflight import ExecutionPreflight

            tenant_id_val = getattr(ctx, "tenant_id", None)
            user_id_val = getattr(ctx, "user_id", None)
            if not user_id_val:
                raise ValueError("No user_id in planner context for agent sub-call")
            if not tenant_id_val:
                raise ValueError("No tenant_id in planner context for agent sub-call")

            sub_exec = await ExecutionPreflight(planner_session).prepare(
                agent_slug=target_slug,
                user_id=uuid.UUID(str(user_id_val)),
                tenant_id=uuid.UUID(str(tenant_id_val)),
                request_text=compact_ctx.goal[:500],
                allow_partial=True,
                platform_config=platform_config,
                sandbox_overrides=sandbox_overrides,
                include_routable_agents=False,
            )

            self._merge_runtime_deps(ctx, sub_exec)

            from app.agents.runtime.agent import AgentToolRuntime

            sub_runtime = AgentToolRuntime(
                llm_client=self._llm_client,
                run_store=self._run_store,
            )

            sub_answer_parts: List[str] = []
            sub_call_failed = False
            sub_call_error: Optional[str] = None

            async for sub_event in sub_runtime.execute(
                exec_request=sub_exec,
                messages=messages,
                ctx=ctx,
                model=model,
                enable_logging=True,
            ):
                if sub_event.type == RuntimeEventType.DELTA:
                    delta = sub_event.data.get("content", "")
                    if delta:
                        sub_answer_parts.append(delta)
                elif sub_event.type in (
                    RuntimeEventType.OPERATION_CALL,
                    RuntimeEventType.OPERATION_RESULT,
                ):
                    yield sub_event
                elif sub_event.type == RuntimeEventType.ERROR:
                    sub_call_failed = True
                    sub_call_error = str(sub_event.data.get("error") or "agent_call_error")
                    yield sub_event

            agent_answer = "".join(sub_answer_parts)
            obs = self._build_observation(
                target_slug, agent_answer, sub_call_failed, sub_call_error
            )
            compact_ctx.update_from_observation(obs, target_slug, "call")

            await memory_service.record_agent_result(
                exec_request.run_id,
                agent_slug=target_slug,
                summary=obs.summary,
                chat_id=getattr(ctx, "chat_id", None),
                tenant_id=getattr(ctx, "tenant_id", None),
                facts=[agent_answer[:500]] if agent_answer and not sub_call_failed else [],
                phase_id=outline_progress.current_phase_id,
                step_id=getattr(next_action, "step_id", None),
            )
            self._update_phase_progress(
                outline_progress,
                execution_outline,
                next_action,
                observation_summary=obs.summary,
                mark_completed=not sub_call_failed,
            )

            yield RuntimeEvent(RuntimeEventType.STATUS, {
                "stage": "phase_progress",
                "current_phase_id": outline_progress.current_phase_id,
                "completed_phase_ids": list(outline_progress.completed_phase_ids),
            })

            if sub_call_failed:
                await run_session.log_step("agent_error", {
                    "agent_slug": target_slug,
                    "error": sub_call_error,
                    "answer_length": len(agent_answer),
                    "iteration": iteration + 1,
                })
                logger.warning(
                    "Planner iter=%s: agent=%s failed (%s), facts=%s",
                    iteration + 1, target_slug, sub_call_error, len(compact_ctx.facts),
                )
            else:
                await run_session.log_step("agent_result", {
                    "agent_slug": target_slug,
                    "answer_length": len(agent_answer),
                    "iteration": iteration + 1,
                })
                logger.info(
                    "Planner iter=%s: agent=%s answered (%s chars), facts=%s",
                    iteration + 1, target_slug, len(agent_answer), len(compact_ctx.facts),
                )

        except Exception as exc:
            logger.error("Agent sub-call to %s failed: %s", target_slug, exc, exc_info=True)
            await run_session.log_step("agent_error", {
                "agent_slug": target_slug,
                "error": str(exc),
                "iteration": iteration + 1,
            })
            yield RuntimeEvent.error(
                f"Agent {target_slug} call failed: {exc}",
                recoverable=True,
            )
            from app.agents.contracts import Observation, ObservationError, ObservationStatus

            obs = Observation(
                status=ObservationStatus.ERROR,
                summary=f"Agent {target_slug} call failed: {exc}",
                error=ObservationError(type="agent_call_error", message=str(exc)),
            )
            compact_ctx.update_from_observation(obs, target_slug, "call")
            await memory_service.record_agent_result(
                exec_request.run_id,
                agent_slug=target_slug,
                summary=obs.summary,
                chat_id=getattr(ctx, "chat_id", None),
                tenant_id=getattr(ctx, "tenant_id", None),
                facts=[],
                phase_id=outline_progress.current_phase_id,
                step_id=getattr(next_action, "step_id", None),
            )
            self._update_phase_progress(
                outline_progress,
                execution_outline,
                next_action,
                observation_summary=obs.summary,
                mark_completed=False,
            )

    @staticmethod
    def _merge_runtime_deps(ctx: "ToolContext", sub_exec: Any) -> None:
        """Merge sub-agent's resolved execution data into the parent context."""
        runtime_deps = ctx.get_runtime_deps()
        sub_graph = getattr(sub_exec, "execution_graph", None)
        if sub_graph:
            if runtime_deps.execution_graph is None:
                runtime_deps.execution_graph = sub_graph
            else:
                existing_graph = runtime_deps.execution_graph
                if hasattr(existing_graph, "merge"):
                    existing_graph.merge(sub_graph)
                    runtime_deps.execution_graph = existing_graph
                else:
                    from app.agents.runtime_graph import RuntimeExecutionGraph

                    merged = RuntimeExecutionGraph.model_validate(existing_graph)
                    merged.merge(sub_graph)
                    runtime_deps.execution_graph = merged

        ctx.set_runtime_deps(runtime_deps)

    @staticmethod
    def _build_observation(
        target_slug: str,
        agent_answer: str,
        sub_call_failed: bool,
        sub_call_error: Optional[str],
    ) -> Any:
        from app.agents.contracts import Observation, ObservationError, ObservationStatus

        return Observation(
            status=ObservationStatus.ERROR if sub_call_failed else ObservationStatus.OK,
            summary=(
                f"Agent {target_slug} call failed: {sub_call_error}"
                if sub_call_failed
                else f"Agent {target_slug} responded: {agent_answer[:300]}"
            ),
            error=ObservationError(
                type="agent_call_error",
                message=sub_call_error or "",
            ) if sub_call_failed else None,
        )
