from types import SimpleNamespace

import pytest

from app.services.platform_settings_service import PlatformSettingsProvider, PlatformSettingsService


class _RepoStub:
    def __init__(self, settings: SimpleNamespace) -> None:
        self._settings = settings

    async def get_or_create(self):
        return self._settings

    async def update(self, settings):
        return settings


@pytest.mark.asyncio
async def test_platform_settings_service_updates_runtime_override_fields():
    settings = SimpleNamespace(
        policies_text=None,
        require_confirmation_for_write=False,
        require_confirmation_for_destructive=False,
        forbid_destructive=False,
        forbid_write_in_prod=False,
        require_backup_before_write=False,
        required_operation_retry_instruction=None,
        operations_rules_text=None,
        intent_messages=None,
        synth_chunk_size=None,
        chat_upload_max_bytes=None,
        chat_upload_allowed_extensions=None,
    )
    service = PlatformSettingsService(session=SimpleNamespace())
    service.repo = _RepoStub(settings)

    PlatformSettingsProvider._cache = {"cached": True}
    await service.update(
        required_operation_retry_instruction="retry text",
        operations_rules_text="rules text",
        intent_messages={"agent_start": "Start"},
        synth_chunk_size=11,
    )

    assert settings.required_operation_retry_instruction == "retry text"
    assert settings.operations_rules_text == "rules text"
    assert settings.intent_messages == {"agent_start": "Start"}
    assert settings.synth_chunk_size == 11
    assert PlatformSettingsProvider._cache is None

