from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.models.execution_limit import ExecutionLimitScope
from app.schemas.execution_limits import ExecutionLimitsUpdate
from app.services.execution_limits_service import (
    CODE_DEFAULT_EXECUTION_LIMITS,
    ExecutionLimitsService,
)


@pytest.mark.asyncio
async def test_entity_scope_inherits_sparse_fields_from_platform():
    service = ExecutionLimitsService(AsyncMock())
    platform = SimpleNamespace(llm_timeout_s=75, agent_llm_calls_max=7)
    agent = SimpleNamespace(llm_timeout_s=None, agent_llm_calls_max=2)
    service._get_scope = AsyncMock(side_effect=[agent, platform])

    resolved = await service.resolve(
        scope_type=ExecutionLimitScope.AGENT,
        scope_ref="direct_answer",
    )

    assert resolved.values.llm_timeout_s == 75
    assert resolved.sources["llm_timeout_s"] == "platform"
    assert resolved.values.agent_llm_calls_max == 2
    assert resolved.sources["agent_llm_calls_max"] == "entity"


@pytest.mark.asyncio
async def test_missing_database_rows_fall_back_to_complete_code_profile():
    service = ExecutionLimitsService(AsyncMock())
    service._get_scope = AsyncMock(return_value=None)

    resolved = await service.resolve(
        scope_type=ExecutionLimitScope.ORCHESTRATOR_ROLE,
        scope_ref="planner",
    )

    assert resolved.values.__dict__ == CODE_DEFAULT_EXECUTION_LIMITS
    assert set(resolved.sources.values()) == {"code"}


@pytest.mark.asyncio
async def test_sandbox_override_cannot_clear_effective_limit():
    service = ExecutionLimitsService(AsyncMock())
    service._get_scope = AsyncMock(return_value=None)

    resolved = await service.resolve(
        scope_type=ExecutionLimitScope.AGENT,
        scope_ref="direct_answer",
        override={"llm_timeout_s": None, "agent_llm_calls_max": 4},
    )

    assert resolved.values.llm_timeout_s == CODE_DEFAULT_EXECUTION_LIMITS["llm_timeout_s"]
    assert resolved.sources["llm_timeout_s"] == "code"
    assert resolved.values.agent_llm_calls_max == 4
    assert resolved.sources["agent_llm_calls_max"] == "sandbox"


def test_execution_limits_update_accepts_real_runtime_columns_and_rejects_stale_names():
    update = ExecutionLimitsUpdate(
        task_attempts_total_max=3,
        agent_tool_calls_max=50,
        execution_wall_time_ms_max=300_000,
    )

    assert update.model_fields_set == {
        "task_attempts_total_max",
        "agent_tool_calls_max",
        "execution_wall_time_ms_max",
    }
    with pytest.raises(ValidationError, match="runtime_steps_max"):
        ExecutionLimitsUpdate(runtime_steps_max=10)
