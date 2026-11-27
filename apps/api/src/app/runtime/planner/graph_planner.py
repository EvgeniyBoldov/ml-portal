"""LLM planner adapter for immutable runtime iterations."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import IterationProposal, PlanRequest
from app.agents.context import ToolContext
from app.runtime.memory.role_tools import RoleMemoryTools
from app.runtime.memory.document_memory import accumulate_document_memory, document_memory, search_receipt
from app.runtime.interaction import InteractionRequester, RuntimeInteraction, InteractionRequired, require_interaction_allowed

from app.runtime.planner.response_contract import PlannerStep
from app.runtime.evidence_projection import prompt_payload_budget, bound_prompt_memory


class TimerPauseRequired(Exception):
    def __init__(self, payload: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        super().__init__("planner requested a durable timer pause")
        self.payload = payload
        self.checkpoint = checkpoint


class GraphPlanner:
    """The model proposes data only; compilation belongs to the runtime."""

    def __init__(self, *, session: Any, llm_client: LLMClientProtocol) -> None:
        self._session = session
        self._llm = StructuredLLMCall(session=session, llm_client=llm_client)
        self._input_builder = PlannerInputBuilder()

    @staticmethod
    def timer_delay_base(payload: dict[str, Any], *, now: datetime) -> datetime:
        """The time base wake_at bounds are measured against.

        The model anchors wake_at on durable_clock, which is captured before
        the LLM roundtrip. Measuring the minimum delay from the post-response
        wall clock would spend the LLM latency and reject honest short timers
        (the user asks for 65 seconds, the model answers 15 seconds later), so
        the bounds use the same time base the model was given.
        """
        clock = payload.get("durable_clock") if isinstance(payload, dict) else None
        if isinstance(clock, dict):
            try:
                return datetime.fromisoformat(str(clock["current_utc_time"]))
            except (KeyError, TypeError, ValueError):
                return now
        return now

    @staticmethod
    def compile_prompt(role_config: dict[str, Any], role_override: Any, *, timer_enabled: bool = False) -> str:
        system_prompt = StructuredLLMCall._compile_role_prompt(
            role_config, role_override if isinstance(role_override, dict) else None, schema=PlannerStep,
        )
        system_prompt += (
            "\nRuntime interaction protocol: when a user decision is necessary, return kind=interaction "
            "with interaction={question: a specific question, response_type: text or boolean}. "
            "Runtime saves this planner checkpoint and returns the typed answer to this planner. "
            "Use interaction_answers as additional context for the original goal; do not repeat answered questions."
        )
        if timer_enabled:
            system_prompt += (
                "\nDurable timer protocol: waiting is your own capability, not an agent or memory tool. "
                "Never return tool_call with tool=wait_until and never assign a waiting task to an agent. "
                "When the requested next step happens at or after a future time (a scheduled check, a reminder, "
                "\"wait N seconds or minutes, then continue\"), return kind=wait_until at the top level with "
                "wait_until={wake_at: timezone-aware, reason, optional next_check and user_update}. "
                "The runtime delivers user_update to the user immediately, sleeps until wake_at, then wakes this "
                "planner with a timer_elapsed continuation and the plan continues. "
                "timer_wake_count in the request says how many timer pauses this run has already completed "
                "(the one just resumed included); continue a multi-step schedule at the step matching that count. "
                "Do not invent a wait if no future wake is needed. The runtime validates timer bounds."
            )
        return system_prompt

    async def plan(
        self,
        *,
        request: PlanRequest,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        event_sink: Optional[Callable[[RuntimeEvent], Awaitable[None]]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        budget_registry: Optional[Any] = None,
        planner_budget_entity_id: Optional[str] = None,
        planner_iteration_trace_id: Optional[str] = None,
        persist_memory: Optional[Callable[[list[dict[str, Any]]], Awaitable[None]]] = None,
        ctx: ToolContext | None = None,
        interaction_answers: list[dict[str, Any]] | None = None,
        proposal_validator: Callable[[IterationProposal], None] | None = None,
        **runtime_context: Any,
    ) -> IterationProposal:
        answers = interaction_answers or []
        matching_answer = next((row for row in reversed(answers)
                                if row.get("interaction", {}).get("requester", {}).get("entity_id") == planner_iteration_trace_id), None)
        resumed = matching_answer["interaction"].get("checkpoint", {}) if matching_answer else {}
        if resumed.get("request"):
            current_memory = request.context.memory_context
            request = PlanRequest.model_validate(resumed["request"])
            request.context.memory_context = current_memory
        request.context.memory_context = accumulate_document_memory(request.context.memory_context, {})
        if event_sink:
            await event_sink(RuntimeEvent.status(
                "memory_context_used",
                entity_type="planner_iteration",
                entity_id=planner_iteration_trace_id,
                memory_owner="planner", memory_owner_id=str(request.plan_id), reason="iteration_started",
                memory_context=request.context.memory_context,
            ))
        tools = RoleMemoryTools(session=self._session, ctx=ctx)
        descriptors = await tools.descriptors()
        audit = dict(runtime_context.get("planner_rbac_audit") or {})
        allowed_agents = set(audit.get("allowed") or [])
        agent_details = audit.get("candidate_agent_details") if isinstance(audit.get("candidate_agent_details"), dict) else {}
        agent_items = []
        for slug in sorted(set(audit.get("candidates") or [])):
            available = slug in allowed_agents
            metadata = agent_details.get(slug) if isinstance(agent_details.get(slug), dict) else {}
            agent_items.append({"kind": "agent", "key": slug, "label": str(metadata.get("label") or slug),
                "status": "available" if available else "unavailable",
                **({"description": metadata["description"]} if metadata.get("description") else {}),
                **({} if available else {"reason_code": "blocked_by_rbac", "reason": "Недоступен по правам доступа"})})
        tool_items = [{"kind": "tool", "key": str(item.get("name") or item.get("tool") or ""),
            "label": str(item.get("label") or item.get("name") or item.get("tool") or "Инструмент"),
            "status": "available",
            **({"description": str(item["description"]).strip()} if item.get("description") else {}),
            "source_label": "Система",
            **({"risk_level": item["risk_level"]} if item.get("risk_level") else {})}
            for item in descriptors if item.get("name") or item.get("tool")]
        if event_sink:
            await event_sink(RuntimeEvent.access_snapshot(
                entity_type="planner", entity_id=planner_iteration_trace_id,
                parent_entity_type="planner_iteration", parent_entity_id=planner_iteration_trace_id,
                items=[*agent_items, *tool_items],
            ))
        role_config = ctx.extra.get("planner_role_config") if ctx is not None else None
        if role_config is None:
            role_config = await self._llm.role_service.get_role_config(SystemLLMRoleType.PLANNER)
        role_override = ((sandbox_overrides or {}).get("role_overrides") or {}).get("planner")
        timer_enabled = runtime_context.get("timer_enabled") is True
        system_prompt = self.compile_prompt(role_config, role_override, timer_enabled=timer_enabled)
        model_name = str((role_override.get("model") if isinstance(role_override, dict) else None)
                         or role_config.get("model") or "unknown")
        prompt_memory_budget = await prompt_payload_budget(session=self._session, model=model_name,
            system_prompt=system_prompt, schema=PlannerStep)
        # Checkpointed file reads are an authorization snapshot that may have
        # become stale while the user was answering. Keep only shared memory
        # search receipts; file and chat reads must be resolved again.
        tool_results: list[dict[str, Any]] = [
            item for item in (resumed.get("tool_results") or [])
            if isinstance(item, dict) and item.get("tool") == "memory.search"
        ]
        timer_checkpoint = runtime_context.get("timer_checkpoint")
        if timer_enabled and isinstance(timer_checkpoint, dict):
            tool_results = [
                item for item in (timer_checkpoint.get("tool_results") or [])
                if isinstance(item, dict) and item.get("tool") == "memory.search"
            ]
        for _ in range(RoleMemoryTools.MAX_CALLS + 1):
            payload = self._input_builder.build_graph_request(request)
            if timer_enabled:
                timezone_name = str(runtime_context.get("durable_timezone") or "UTC")
                try:
                    local_now = datetime.now(ZoneInfo(timezone_name))
                except Exception:
                    timezone_name, local_now = "UTC", datetime.now(timezone.utc)
                payload["durable_clock"] = {
                    "timezone": timezone_name,
                    "current_local_time": local_now.isoformat(),
                    "current_utc_time": datetime.now(timezone.utc).isoformat(),
                }
                wake_count = runtime_context.get("timer_pause_count")
                if isinstance(wake_count, int) and wake_count > 0:
                    # Multi-step schedules must continue at the right step:
                    # tell the model which timer wake this round is.
                    payload["timer_wake_count"] = wake_count
            state = ctx.extra.get("runtime_turn_state") if ctx else None
            if state is not None:
                from app.runtime.prompt_projections import selected_materials
                payload["run_context"] = selected_materials(state.run_context.projection(scope_keys=list(request.context.scope_context.get("keys") or [])))
            # Argument schemas already live in PlannerStep.tool_call.
            payload["planner_tools"] = [{key: value for key, value in descriptor.items() if key != "input_schema"}
                                        for descriptor in descriptors]
            payload["memory_tool_results"] = list(tool_results)
            payload["memory_tool_calls_remaining"] = RoleMemoryTools.MAX_CALLS - len(tool_results)
            payload["interaction_answers"] = [{"question": row["interaction"]["question"], "response": row["response"]} for row in answers]
            if prompt_memory_budget is not None:
                payload = bound_prompt_memory(payload, token_budget=prompt_memory_budget,
                                              model=model_name)
            def validate_step(step: PlannerStep) -> None:
                if step.kind == "wait_until":
                    if not timer_enabled:
                        raise ValueError("wait_until is only enabled for durable runs")
                    assert step.wait_until is not None
                    configured_pause_limit = runtime_context.get("timer_pause_limit")
                    pause_limit = max(0, int(100 if configured_pause_limit is None else configured_pause_limit))
                    pause_count = max(0, int(runtime_context.get("timer_pause_count") or 0))
                    if pause_count >= pause_limit:
                        raise ValueError(f"timer pause limit of {pause_limit} has been reached")
                    now = datetime.now(timezone.utc)
                    anchor = self.timer_delay_base(payload, now=now)
                    min_delay = max(0, int(runtime_context.get("timer_min_delay_seconds") or 60))
                    max_horizon = max(min_delay + 1, int(runtime_context.get("timer_max_horizon_seconds") or 2_592_000))
                    delay = (step.wait_until.wake_at - anchor).total_seconds()
                    if delay < min_delay:
                        raise ValueError(
                            f"wake_at must be at least {min_delay} seconds after the current_utc_time supplied to you"
                        )
                    if delay > max_horizon:
                        raise ValueError(f"wake_at must be within {max_horizon} seconds")
                if step.kind != "proposal":
                    return
                proposal = step.to_runtime_proposal(goal=request.context.goal)
                if proposal_validator is not None:
                    proposal_validator(proposal)

            durable_segment = getattr(ctx, "extra", {}).get("durable_segment") if ctx is not None else None
            if durable_segment is not None:
                await durable_segment.fence_effect()
            result = await self._llm.invoke(
                role=SystemLLMRoleType.PLANNER,
                payload=payload,
                schema=PlannerStep,
                validation_context={"planner_execution_ledger": request.context.execution_ledger},
                output_validator=validate_step,
                system_prompt=system_prompt,
                role_config=role_config,
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_execution_id=None,
                trace_parent_entity_type="planner_iteration",
                trace_parent_entity_id=planner_iteration_trace_id,
                event_sink=event_sink,
                sandbox_overrides=sandbox_overrides,
                budget_registry=budget_registry,
                budget_entity_id=planner_budget_entity_id,
            )
            step = result.value
            if step.kind == "interaction":
                require_interaction_allowed(ctx, "planner")
                assert step.interaction is not None
                raise InteractionRequired(RuntimeInteraction.create(step.interaction,
                    InteractionRequester(stage="planner", entity_id=str(planner_iteration_trace_id), plan_id=str(request.plan_id)),
                    checkpoint={"request": request.model_dump(mode="json"), "tool_results": tool_results}))
            if step.kind == "proposal":
                assert step.proposal is not None
                return step.to_runtime_proposal(goal=request.context.goal)
            if step.kind == "wait_until":
                if not timer_enabled:
                    raise RuntimeError("planner returned wait_until outside a durable timer-enabled run")
                assert step.wait_until is not None
                raise TimerPauseRequired(
                    step.wait_until.model_dump(mode="json"),
                    {"request": request.model_dump(mode="json"), "tool_results": tool_results},
                )
            call = step.tool_call
            assert call is not None
            if len(tool_results) >= RoleMemoryTools.MAX_CALLS:
                raise RuntimeError("planner memory tool-call limit exceeded without IterationProposal")
            record = await tools.execute(call, actor="planner", parent_type="planner_iteration",
                                         parent_id=planner_iteration_trace_id, event_sink=event_sink)
            data = record["result"]
            tool_results.append(search_receipt(record) if call.tool == "memory.search" else record)
            if call.tool == "memory.search":
                request.context.memory_context = accumulate_document_memory(request.context.memory_context, data)
            request.context.planner_search_results = document_memory(request.context.memory_context)
            if persist_memory:
                await persist_memory(request.context.memory_context)
            if event_sink:
                await event_sink(RuntimeEvent.status(
                    "memory_context_used", entity_type="planner_iteration", entity_id=planner_iteration_trace_id,
                    memory_owner="planner", memory_owner_id=str(request.plan_id), reason="search_completed",
                    memory_context=request.context.memory_context,
                ))
        raise RuntimeError("planner memory tool-call limit exceeded without IterationProposal")
