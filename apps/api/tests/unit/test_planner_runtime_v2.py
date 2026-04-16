from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.agents.contracts import (
    ActionMeta,
    ActionType,
    ExecutionOutline,
    FinalPayload,
    NextAction,
    OutlinePhase,
    PolicyDecisionType,
)
from app.agents.runtime.events import RuntimeEventType
from app.agents.runtime.logging import LoggingLevel
from app.agents.runtime.planner import PlannerRuntime


@pytest.mark.asyncio
async def test_planner_blocks_final_until_required_phases_complete():
    runtime = PlannerRuntime(llm_client=MagicMock(), run_store=AsyncMock())
    runtime.config_resolver.resolve = AsyncMock(
        return_value=(
            SimpleNamespace(
                max_steps=2,
                max_wall_time_ms=10_000,
                max_tool_calls_total=5,
                tool_timeout_ms=5_000,
                max_retries=1,
            ),
            SimpleNamespace(model=None, temperature=0.0, max_tokens=128),
            {"policies_text": "default"},
        )
    )
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=LoggingLevel.BRIEF)
    runtime._create_run_session = MagicMock(return_value=SimpleNamespace(
        run_id="run-1",
        start=AsyncMock(),
        finish=AsyncMock(),
        log_step=AsyncMock(),
    ))

    exec_request = SimpleNamespace(
        run_id=uuid4(),
        agent=SimpleNamespace(slug="planner-agent", logging_level="brief"),
        available_actions=SimpleNamespace(agents=[SimpleNamespace(agent_slug="rag-search", description="")]),
    )
    planner_session = AsyncMock()

    class _SessionFactory:
        async def __aenter__(self):
            return planner_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=uuid4(),
        extra={},
    ).with_runtime_deps(
        session_factory=lambda: _SessionFactory(),
        execution_outline=ExecutionOutline(
            goal="Compare docs",
            phases=[
                OutlinePhase(
                    phase_id="collect_context",
                    title="Collect context",
                    objective="Collect context",
                    must_do=True,
                    allow_final_after=False,
                ),
                OutlinePhase(
                    phase_id="finalize",
                    title="Finalize",
                    objective="Finalize",
                    must_do=True,
                    allow_final_after=True,
                ),
            ],
        ).model_dump(),
        helper_summary={"goal": "Compare docs", "facts": []},
    )
    messages = [{"role": "user", "content": "compare docs"}]

    final_action = NextAction(
        type=ActionType.FINAL,
        final=FinalPayload(answer="Premature final"),
        meta=ActionMeta(why="Enough info"),
    )

    with patch("app.agents.policy_engine.PolicyEngine.from_platform_config") as policy_factory, patch(
        "app.agents.runtime.planner.SystemLLMExecutor"
    ) as executor_cls, patch(
        "app.agents.runtime.planner.ExecutionMemoryService"
    ) as memory_service_cls:
        policy_factory.return_value = SimpleNamespace(
            evaluate=MagicMock(return_value=SimpleNamespace(decision=PolicyDecisionType.ALLOW, reason="ok"))
        )
        executor_cls.return_value.execute_planner_with_fallback = AsyncMock(return_value=final_action)
        memory_service = AsyncMock()
        memory_service_cls.return_value = memory_service
        memory_service.get_or_create = AsyncMock()
        memory_service.update_context = AsyncMock()
        memory_service.snapshot = AsyncMock(return_value={})
        memory_service.finish_run = AsyncMock()

        events = [
            event
            async for event in runtime.execute(
                exec_request=exec_request,
                messages=messages,
                ctx=ctx,
                model=None,
                enable_logging=False,
            )
        ]

    blocked_index = next(
        (
            idx
            for idx, event in enumerate(events)
            if event.type == RuntimeEventType.STATUS and event.data.get("stage") == "final_blocked"
        ),
        None,
    )
    assert blocked_index is not None

    final_index = next((idx for idx, event in enumerate(events) if event.type == RuntimeEventType.FINAL), None)
    if final_index is not None:
        assert blocked_index < final_index
