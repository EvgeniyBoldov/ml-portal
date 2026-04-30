from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.runtime_config_service import RuntimeConfigService


@pytest.mark.asyncio
async def test_runtime_config_service_returns_platform_config(mock_session):
    platform_provider = type("PlatformProvider", (), {})()
    platform_provider.get_config = AsyncMock(
        return_value={
            "policies_text": "policy",
            "require_confirmation_for_write": True,
        }
    )

    with patch(
        "app.services.runtime_config_service.PlatformSettingsProvider.get_instance",
        return_value=platform_provider,
    ):
        service = RuntimeConfigService(mock_session)
        config = await service.get_pipeline_config()

    assert config["policies_text"] == "policy"
    assert config["require_confirmation_for_write"] is True


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
