from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.runtime_limits_service import AGENT_CODE_DEFAULTS, ModelCallLimits, RuntimeLimitsService


@pytest.mark.asyncio
async def test_actor_inherits_sparse_defaults():
    service = RuntimeLimitsService(AsyncMock())
    service._actor_row = AsyncMock(side_effect=[SimpleNamespace(llm_calls_max=2), SimpleNamespace(llm_calls_max=7, wall_time_ms_max=75000)])
    resolved = await service.resolve_agent("network")
    assert resolved.effective.llm_calls_max == 2
    assert resolved.sources["llm_calls_max"] == "entity"
    assert resolved.effective.wall_time_ms_max == 75000
    assert resolved.sources["wall_time_ms_max"] == "default"


@pytest.mark.asyncio
async def test_missing_rows_use_complete_defaults():
    service = RuntimeLimitsService(AsyncMock())
    service._actor_row = AsyncMock(return_value=None)
    resolved = await service.resolve_agent("network")
    assert vars(resolved.effective) == AGENT_CODE_DEFAULTS
    assert set(resolved.sources.values()) == {"code"}


@pytest.mark.asyncio
async def test_sandbox_overrides_cannot_disable_actor_limits():
    service = RuntimeLimitsService(AsyncMock())
    service._actor_row = AsyncMock(return_value=None)
    resolved = await service.resolve_agent("network", {"llm_calls_max": 4, "wall_time_ms_max": None, "tool_calls_max": 0})
    assert resolved.effective.llm_calls_max == 4
    assert resolved.sources["llm_calls_max"] == "sandbox"
    assert resolved.effective.tool_calls_max == AGENT_CODE_DEFAULTS["tool_calls_max"]


@pytest.mark.asyncio
async def test_model_transport_limits_allow_zero_retries():
    result = SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(request_timeout_s=75, max_retries=0))
    service = RuntimeLimitsService(SimpleNamespace(execute=AsyncMock(return_value=result)))
    assert await service.resolve_model("local") == ModelCallLimits(request_timeout_s=75, max_retries=0)


@pytest.mark.asyncio
async def test_model_transport_fallback():
    result = SimpleNamespace(scalar_one_or_none=lambda: None)
    service = RuntimeLimitsService(SimpleNamespace(execute=AsyncMock(return_value=result)))
    assert await service.resolve_model(None) == ModelCallLimits()
