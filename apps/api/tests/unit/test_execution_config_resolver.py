from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.execution_config_resolver import ExecutionConfigResolver


class _FakeModelResolver:
    def __init__(self, _session) -> None:
        pass

    async def resolve(self, alias):  # noqa: ANN001
        mapping = {
            "llm.bad": "llm.bad",
            "llm.good": "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-scout-17b-16e-instruct": "meta-llama/llama-4-scout-17b-16e-instruct",
        }
        return mapping.get(alias, alias)


@pytest.mark.asyncio
async def test_resolve_model_alias_falls_back_to_platform_default(monkeypatch):
    monkeypatch.setattr(
        "app.services.model_resolver.ModelResolver",
        _FakeModelResolver,
    )
    resolved = await ExecutionConfigResolver._resolve_model_alias(
        AsyncMock(),
        "llm.bad",
        default_alias="llm.good",
    )
    assert resolved == "meta-llama/llama-4-scout-17b-16e-instruct"


@pytest.mark.asyncio
async def test_resolve_model_alias_keeps_resolved_provider_name(monkeypatch):
    monkeypatch.setattr(
        "app.services.model_resolver.ModelResolver",
        _FakeModelResolver,
    )
    resolved = await ExecutionConfigResolver._resolve_model_alias(
        AsyncMock(),
        "meta-llama/llama-4-scout-17b-16e-instruct",
        default_alias="llm.good",
    )
    assert resolved == "meta-llama/llama-4-scout-17b-16e-instruct"
