from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.runtime_config_service import RuntimeConfigService


@pytest.mark.asyncio
async def test_runtime_config_service_merges_orchestration_fail_policy(mock_session):
    platform_provider = type("PlatformProvider", (), {})()
    platform_provider.get_config = AsyncMock(
        return_value={
            "policies_text": "policy",
            "preflight_fail_open": False,
        }
    )
    orchestration_provider = type("OrchestrationProvider", (), {})()
    orchestration_provider.get_config = AsyncMock(
        return_value={
            "preflight_fail_open": True,
            "planner_fail_open_message": "planner fallback",
        }
    )

    with patch(
        "app.services.runtime_config_service.PlatformSettingsProvider.get_instance",
        return_value=platform_provider,
    ), patch(
        "app.services.runtime_config_service.OrchestrationSettingsProvider.get_instance",
        return_value=orchestration_provider,
    ):
        service = RuntimeConfigService(mock_session)
        config = await service.get_pipeline_config()

    assert config["policies_text"] == "policy"
    assert config["preflight_fail_open"] is True
    assert config["planner_fail_open_message"] == "planner fallback"


@pytest.mark.asyncio
async def test_runtime_config_service_ignores_orchestration_merge_error(mock_session):
    platform_provider = type("PlatformProvider", (), {})()
    platform_provider.get_config = AsyncMock(return_value={"policies_text": "policy"})
    orchestration_provider = type("OrchestrationProvider", (), {})()
    orchestration_provider.get_config = AsyncMock(side_effect=RuntimeError("boom"))

    with patch(
        "app.services.runtime_config_service.PlatformSettingsProvider.get_instance",
        return_value=platform_provider,
    ), patch(
        "app.services.runtime_config_service.OrchestrationSettingsProvider.get_instance",
        return_value=orchestration_provider,
    ):
        service = RuntimeConfigService(mock_session)
        config = await service.get_pipeline_config()

    assert config == {"policies_text": "policy"}


@pytest.mark.asyncio
async def test_runtime_config_service_returns_empty_on_partial_env_attr_error(mock_session):
    platform_provider = type("PlatformProvider", (), {})()
    platform_provider.get_config = AsyncMock(side_effect=AttributeError("coroutine has no attribute execute"))

    with patch(
        "app.services.runtime_config_service.PlatformSettingsProvider.get_instance",
        return_value=platform_provider,
    ):
        service = RuntimeConfigService(mock_session)
        config = await service.get_pipeline_config()

    assert config == {}
