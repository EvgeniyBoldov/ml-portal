"""LLM planner adapter for immutable runtime iterations."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Literal, Optional
from uuid import UUID, uuid4
from hashlib import sha256
import json

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.orchestrator_contracts import IterationProposal, PlanRequest
from app.runtime.memory.search import MemorySearchService
from app.runtime.memory.search_contract import MemorySearchInput
from app.runtime.memory.mechanical_lookup import MechanicalLookupService
from pydantic import BaseModel, Field, model_validator


class PlannerMemoryToolCall(MemorySearchInput):
    operation: Literal["memory.search", "memory.lookup"]


class PlannerStep(BaseModel):
    """One direct planner decision: contextual read or persisted proposal."""
    kind: Literal["tool_call", "proposal"]
    tool_call: PlannerMemoryToolCall | None = None
    proposal: IterationProposal | None = None
    model_config = {"extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_proposal(cls, value: Any) -> Any:
        # Existing operator-managed planner prompts may still instruct the
        # former bare IterationProposal contract during rollout.  Treat that
        # exact shape as a proposal, without accepting arbitrary free-form
        # payloads.
        if isinstance(value, dict) and "kind" not in value and "terminal" in value:
            return {"kind": "proposal", "proposal": value}
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> "PlannerStep":
        if self.kind == "tool_call" and self.tool_call is None:
            raise ValueError("tool_call step requires tool_call")
        if self.kind == "proposal" and self.proposal is None:
            raise ValueError("proposal step requires proposal")
        if self.kind == "tool_call" and self.proposal is not None:
            raise ValueError("tool_call step cannot contain proposal")
        if self.kind == "proposal" and self.tool_call is not None:
            raise ValueError("proposal step cannot contain tool_call")
        return self


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
        **_: Any,
    ) -> IterationProposal:
        if event_sink:
            await event_sink(RuntimeEvent.status(
                "memory_context_used",
                entity_type="planner_iteration",
                entity_id=planner_iteration_trace_id,
                memory_context=request.context.memory_context,
            ))
        payload = self._input_builder.build_graph_request(request)
        payload["planner_tools"] = [{
            "operation": "memory.search",
            "description": (
                "Read bounded ACL-scoped project/company memory and confirmed glossary terms "
                "before proposing tasks. Use it for long memory or abbreviations; "
                "Use scopes=user/tenant for confirmed owned facts omitted from the initial profile; fact_subject selects an exact subject."
            ),
        }, {"operation": "memory.lookup", "description": "Find published scope and glossary candidates by name or alias; returns identities only."}]
        role_config = await self._llm.role_service.get_role_config(SystemLLMRoleType.PLANNER)
        # Editable role instructions and the generated protocol use one compiler.
        role_override = ((sandbox_overrides or {}).get("role_overrides") or {}).get(
            SystemLLMRoleType.PLANNER.value,
        )
        system_prompt = self._llm._compile_role_prompt(
            role_config, role_override if isinstance(role_override, dict) else None, schema=PlannerStep,
        )
        tool_results: list[dict[str, Any]] = []
        for _ in range(4):
            payload["memory_tool_results"] = tool_results
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
            if step.kind == "proposal":
                assert step.proposal is not None
                return step.proposal
            call = step.tool_call
            assert call is not None
            if len(tool_results) >= 3:
                raise RuntimeError("planner memory tool-call limit exceeded without IterationProposal")
            call_id = f"planner-memory-search-{uuid4()}"
            arguments = call.model_dump(exclude={"operation"})
            if event_sink:
                await event_sink(RuntimeEvent.tool_call(
                    tool=call.operation, call_id=call_id, arguments=arguments,
                    parent_entity_type="planner_iteration",
                    parent_entity_id=planner_iteration_trace_id,
                    actor_type="planner", actor_entity_id=planner_iteration_trace_id,
                ))
            try:
                effective_keys = list(request.context.scope_context.get("keys") or [])
                if call.operation == "memory.lookup":
                    data = await MechanicalLookupService(self._session).lookup(query=call.query,
                                                                               tenant_id=tenant_id)
                else:
                    data = await MemorySearchService(self._session).search(
                        query=call.query, tenant_id=tenant_id, user_id=user_id, project_keys=call.project_keys,
                        context_scope_keys=effective_keys, enforce_context=True,
                        team_keys=call.team_keys,
                        scopes=call.scopes,
                        kinds=call.kinds, entity_ids=call.entity_ids,
                        direction=call.direction, limit=call.limit, fact_subject=call.fact_subject,
                    )
            except Exception as exc:
                if event_sink:
                    await event_sink(RuntimeEvent.tool_result(
                        tool=call.operation, call_id=call_id, success=False, data={},
                        error_code="memory_search_failed", safe_message="Не удалось прочитать память",
                        parent_entity_type="planner_iteration",
                        parent_entity_id=planner_iteration_trace_id,
                        actor_type="planner", actor_entity_id=planner_iteration_trace_id,
                    ))
                raise RuntimeError("planner memory search failed") from exc
            if event_sink:
                await event_sink(RuntimeEvent.tool_result(
                    tool=call.operation, call_id=call_id, success=data.get("success") is not False, data=data,
                    parent_entity_type="planner_iteration",
                    parent_entity_id=planner_iteration_trace_id,
                    actor_type="planner", actor_entity_id=planner_iteration_trace_id,
                ))
            tool_results.append({"operation": call.operation, "arguments": call.model_dump(exclude={"operation"}), "result": data})
            if data.get("success") is False:
                continue
            digest = sha256(json.dumps({"operation": call.operation, "arguments": arguments,
                "scope_keys": sorted(request.context.scope_context.get("keys") or [])},
                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            request.context.planner_search_results.append({
                "type": "planner_memory_result", "query_key": digest,
                "operation": call.operation, "query": call.query[:300], "result": data,
            })
            request.context.memory_context.append(request.context.planner_search_results[-1])
        raise RuntimeError("planner memory tool-call limit exceeded without IterationProposal")
