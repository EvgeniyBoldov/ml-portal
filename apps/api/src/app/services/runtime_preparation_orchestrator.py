from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime.events import RuntimeEvent, RuntimeEventType


@dataclass
class RuntimePreparationOutcome:
    execution_outline: Any
    helper_summary: Any
    outline_event: RuntimeEvent


class RuntimePreparationOrchestrator:
    """Prepare runtime dependencies and build execution outline payloads."""

    def prepare(
        self,
        *,
        request_text: str,
        messages: List[Dict[str, Any]],
        triage_result: Any,
        platform_config: Dict[str, Any],
        exec_request: Any,
        ctx: Any,
        ctx_get_runtime_deps: Callable[[Any], Any],
        ctx_set_runtime_deps: Callable[[Any, Any], None],
        get_session_factory: Callable[[], Any],
        helper_summary_service: Any,
        execution_outline_service: Any,
    ) -> RuntimePreparationOutcome:
        runtime_deps = ctx_get_runtime_deps(ctx)
        runtime_deps.operation_executor = DirectOperationExecutor()
        if not getattr(runtime_deps, "session_factory", None):
            try:
                runtime_deps.session_factory = get_session_factory()
            except RuntimeError:
                runtime_deps.session_factory = None
        if getattr(exec_request, "execution_graph", None):
            runtime_deps.execution_graph = exec_request.execution_graph
        ctx_set_runtime_deps(ctx, runtime_deps)

        if getattr(exec_request, "effective_permissions", None):
            denied_reasons = exec_request.effective_permissions.denied_reasons or {}
            ctx.denied_tools = list(denied_reasons.keys())
            ctx.denied_reasons = denied_reasons

        helper_summary = helper_summary_service.build(request_text=request_text, messages=messages)
        execution_outline = execution_outline_service.build(
            request_text=request_text,
            triage_result=triage_result.model_dump() if hasattr(triage_result, "model_dump") else dict(triage_result),
            available_agent_slugs=[
                agent.agent_slug for agent in exec_request.available_actions.agents
            ] if getattr(exec_request, "available_actions", None) else [],
            platform_config=platform_config,
        )
        runtime_deps = ctx_get_runtime_deps(ctx)
        runtime_deps.helper_summary = helper_summary.model_dump()
        runtime_deps.execution_outline = execution_outline.model_dump()
        ctx_set_runtime_deps(ctx, runtime_deps)
        if isinstance(getattr(ctx, "extra", None), dict):
            ctx.extra["helper_summary"] = runtime_deps.helper_summary
            ctx.extra["execution_outline"] = runtime_deps.execution_outline

        outline_event = RuntimeEvent(
            RuntimeEventType.STATUS,
            {
                "stage": "outline_ready",
                "outline_mode": execution_outline.mode.value,
                "outline_phases": [phase.phase_id for phase in execution_outline.phases],
            },
        )
        return RuntimePreparationOutcome(
            execution_outline=execution_outline,
            helper_summary=helper_summary,
            outline_event=outline_event,
        )
