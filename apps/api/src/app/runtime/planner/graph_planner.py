"""LLM planner adapter for immutable runtime iterations."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import UUID

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


class GraphPlanner:
    """The model proposes data only; compilation belongs to the runtime."""

    def __init__(self, *, session: Any, llm_client: LLMClientProtocol) -> None:
        self._session = session
        self._llm = StructuredLLMCall(session=session, llm_client=llm_client)
        self._input_builder = PlannerInputBuilder()

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
        **_: Any,
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
        role_config = await self._llm.role_service.get_role_config(SystemLLMRoleType.PLANNER)
        # Editable role instructions and the generated protocol use one compiler.
        role_override = ((sandbox_overrides or {}).get("role_overrides") or {}).get(
            SystemLLMRoleType.PLANNER.value,
        )
        system_prompt = self._llm._compile_role_prompt(
            role_config, role_override if isinstance(role_override, dict) else None, schema=PlannerStep,
        )
        system_prompt += (
            "\nRuntime interaction protocol: when a user decision is necessary, return kind=interaction "
            "with interaction={question: a specific question, response_type: text or boolean}. "
            "Runtime saves this planner checkpoint and returns the typed answer to this planner. "
            "Use interaction_answers as additional context for the original goal; do not repeat answered questions."
        )
        # Checkpointed file reads are an authorization snapshot that may have
        # become stale while the user was answering. Keep only shared memory
        # search receipts; file and chat reads must be resolved again.
        tool_results: list[dict[str, Any]] = [
            item for item in (resumed.get("tool_results") or [])
            if isinstance(item, dict) and item.get("tool") == "memory.search"
        ]
        for _ in range(RoleMemoryTools.MAX_CALLS + 1):
            payload = self._input_builder.build_graph_request(request)
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
            result = await self._llm.invoke(
                role=SystemLLMRoleType.PLANNER,
                payload=payload,
                schema=PlannerStep,
                system_prompt=system_prompt,
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
