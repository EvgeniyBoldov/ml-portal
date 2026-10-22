from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.services.orchestration_service import OrchestrationService, OrchestrationSettingsProvider


@pytest.mark.asyncio
async def test_get_creates_singleton_settings_when_missing():
    session = AsyncMock()
    session.add = Mock()
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    service = OrchestrationService(session)

    settings = await service.get()

    assert settings.executor_model is None
    assert settings.executor_temperature is None
    session.add.assert_called_once_with(settings)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_executor_applies_allowed_values_and_invalidates_provider_cache():
    session = AsyncMock()
    settings = SimpleNamespace(executor_model="old", executor_temperature=0.2)
    service = OrchestrationService(session)
    service.get = AsyncMock(return_value=settings)
    OrchestrationSettingsProvider._settings_cache = {"executor_model": "cached"}

    try:
        updated = await service.update_executor({
            "executor_model": "llm.primary",
            "executor_temperature": 0.6,
            "unknown_field": "ignored",
        })

        assert updated is settings
        assert settings.executor_model == "llm.primary"
        assert settings.executor_temperature == 0.6
        assert not hasattr(settings, "unknown_field")
        session.flush.assert_awaited_once()
        assert OrchestrationSettingsProvider._settings_cache is None
    finally:
        OrchestrationSettingsProvider.invalidate_cache()
