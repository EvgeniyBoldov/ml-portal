from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.agents.context import ToolContext
from app.agents.runtime.events import RuntimeEventType
from app.services.runtime_preparation_orchestrator import RuntimePreparationOrchestrator


class _Dumpable:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return dict(self._payload)


def test_runtime_preparation_orchestrator_populates_ctx_and_outline_event():
    orchestrator = RuntimePreparationOrchestrator()
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), extra={})
    exec_request = SimpleNamespace(
        execution_graph={"nodes": []},
        effective_permissions=SimpleNamespace(denied_reasons={"x": "deny"}),
        available_actions=SimpleNamespace(agents=[SimpleNamespace(agent_slug="a1")]),
    )
    triage_result = _Dumpable({"type": "orchestrate"})

    helper_summary = _Dumpable({"goal": "g"})
    execution_outline = SimpleNamespace(
        mode=SimpleNamespace(value="multi_agent"),
        phases=[SimpleNamespace(phase_id="p1"), SimpleNamespace(phase_id="p2")],
        model_dump=lambda: {"mode": "multi_agent"},
    )

    helper_summary_service = SimpleNamespace(build=lambda **kwargs: helper_summary)
    execution_outline_service = SimpleNamespace(build=lambda **kwargs: execution_outline)

    outcome = orchestrator.prepare(
        request_text="q",
        messages=[{"role": "user", "content": "q"}],
        triage_result=triage_result,
        platform_config={},
        exec_request=exec_request,
        ctx=ctx,
        ctx_get_runtime_deps=lambda c: c.get_runtime_deps(),
        ctx_set_runtime_deps=lambda c, deps: c.set_runtime_deps(deps),
        get_session_factory=lambda: "factory",
        helper_summary_service=helper_summary_service,
        execution_outline_service=execution_outline_service,
    )

    runtime_deps = ctx.get_runtime_deps()
    assert runtime_deps.session_factory == "factory"
    assert runtime_deps.execution_graph == {"nodes": []}
    assert runtime_deps.helper_summary == {"goal": "g"}
    assert runtime_deps.execution_outline == {"mode": "multi_agent"}
    assert ctx.denied_tools == ["x"]
    assert ctx.denied_reasons == {"x": "deny"}

    assert outcome.outline_event.type == RuntimeEventType.STATUS
    assert outcome.outline_event.data["stage"] == "outline_ready"
    assert outcome.outline_event.data["outline_mode"] == "multi_agent"
    assert outcome.outline_event.data["outline_phases"] == ["p1", "p2"]
