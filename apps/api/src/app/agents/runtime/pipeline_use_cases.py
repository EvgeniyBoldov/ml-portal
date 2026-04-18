"""Runtime pipeline use-cases.

Extracted use-cases keep RuntimePipeline as coordinator and isolate stage logic.
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.agents.contracts import RuntimeTriageDecision
from app.agents.runtime.events import RuntimeEvent
from app.schemas.system_llm_roles import TriageInput
from app.services.orchestration_contract import (
    intent_from_runtime_triage,
    runtime_triage_from_intent,
)
from app.services.system_llm_executor import SystemLLMExecutor

if TYPE_CHECKING:
    from uuid import UUID
    from app.agents.context import ToolContext
    from app.agents.execution_preflight import ExecutionPreflight, ExecutionRequest
    from app.agents.runtime import AgentRuntime
    from app.core.http.clients import LLMClientProtocol


class TriageUseCase:
    """Run triage model and normalize result contract."""

    def __init__(self, session: Any, llm_client: "LLMClientProtocol") -> None:
        self.session = session
        self.llm_client = llm_client

    async def execute(
        self,
        *,
        request_text: str,
        messages: List[Dict[str, Any]],
        platform_config: Dict[str, Any],
        routable_agents: Optional[List[Any]] = None,
    ) -> RuntimeTriageDecision:
        executor = SystemLLMExecutor(self.session, self.llm_client)
        policies_text = platform_config.get("policies_text") or "default"

        conversation_parts: List[str] = []
        for message in messages[-5:]:
            content = message.get("content", "")
            if isinstance(content, dict):
                content = content.get("text", str(content))
            conversation_parts.append(str(content))

        agents_list = [
            {
                "slug": agent.slug,
                "name": agent.name,
                "description": agent.description or "",
            }
            for agent in list(routable_agents or [])
        ]

        triage_input = TriageInput(
            user_message=request_text,
            conversation_summary="\n".join(conversation_parts[-3:]),
            session_state={"status": "active"},
            available_agents=agents_list,
            policies=policies_text,
            active_run=None,
        )
        triage_result, trace_id = await executor.execute_triage(triage_input)
        runtime_decision = RuntimeTriageDecision(
            type=triage_result.type,
            confidence=triage_result.confidence,
            answer=getattr(triage_result, "answer", None),
            clarify_prompt=getattr(triage_result, "clarify_prompt", None),
            goal=getattr(triage_result, "goal", None),
            inputs=getattr(triage_result, "inputs", None) or {},
            trace_id=str(trace_id) if trace_id else None,
        )
        # Normalize through orchestration contract to keep one canonical intent shape.
        return runtime_triage_from_intent(intent_from_runtime_triage(runtime_decision))


class PrepareExecutionUseCase:
    """Prepare execution request via preflight."""

    def __init__(self, preflight: "ExecutionPreflight") -> None:
        self.preflight = preflight

    async def execute(
        self,
        *,
        agent_slug: str,
        user_id: "UUID",
        tenant_id: "UUID",
        request_text: str,
        allow_partial: bool,
        agent_version_id: Optional["UUID"],
        platform_config: Dict[str, Any],
        sandbox_overrides: Dict[str, Any],
        include_routable_agents: bool,
        routable_agents_override: Optional[List[Any]],
        effective_permissions_override: Optional[Any],
    ) -> "ExecutionRequest":
        return await self.preflight.prepare(
            agent_slug=agent_slug,
            user_id=user_id,
            tenant_id=tenant_id,
            request_text=request_text,
            allow_partial=allow_partial,
            agent_version_id=agent_version_id,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
            include_routable_agents=include_routable_agents,
            routable_agents_override=routable_agents_override,
            effective_permissions_override=effective_permissions_override,
        )


class ExecutePlannerUseCase:
    """Stream planner runtime events."""

    def __init__(self, runtime: "AgentRuntime") -> None:
        self.runtime = runtime

    async def execute(
        self,
        *,
        exec_request: "ExecutionRequest",
        messages: List[Dict[str, Any]],
        ctx: "ToolContext",
        model: Optional[str],
        enable_logging: bool,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        async for event in self.runtime.run_sequential_planner(
            exec_request=exec_request,
            messages=messages,
            ctx=ctx,
            model=model,
            enable_logging=enable_logging,
        ):
            yield event
