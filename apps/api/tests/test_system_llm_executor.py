"""
Compatibility tests for the former SystemLLMExecutor surface.

`app.services.system_llm_executor` was removed during runtime refactor.
The active structured execution path is `StructuredLLMCall`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall


class _TriageOut(BaseModel):
    type: str
    confidence: float = 0.0


def _role_cfg(**overrides):
    base = {
        "prompt": "You are triage",
        "model": "test-model",
        "temperature": 0.0,
        "max_tokens": 256,
        "timeout_s": 5,
        "max_retries": 2,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_structured_call_success_with_direct_json():
    llm = SimpleNamespace(chat=AsyncMock(return_value='{"type":"plan","confidence":0.9}'))
    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(return_value=_role_cfg()),
    ):
        call = StructuredLLMCall(session=AsyncMock(), llm_client=llm)
        result = await call.invoke(
            role=SystemLLMRoleType.TRIAGE,
            payload={"user_message": "hi"},
            schema=_TriageOut,
        )

    assert result.value.type == "plan"
    assert result.value.confidence == 0.9
    assert result.trace_id is None
    llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_structured_call_extracts_markdown_json():
    llm = SimpleNamespace(
        chat=AsyncMock(return_value="text\n```json\n{\"type\":\"final\",\"confidence\":0.4}\n```")
    )
    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(return_value=_role_cfg()),
    ):
        call = StructuredLLMCall(session=AsyncMock(), llm_client=llm)
        result = await call.invoke(
            role=SystemLLMRoleType.TRIAGE,
            payload={"user_message": "hello"},
            schema=_TriageOut,
        )

    assert result.value.type == "final"
    assert result.value.confidence == 0.4


@pytest.mark.asyncio
async def test_structured_call_retries_then_succeeds():
    llm = SimpleNamespace(
        chat=AsyncMock(
            side_effect=[
                Exception("temporary upstream error"),
                '{"type":"plan","confidence":0.7}',
            ]
        )
    )
    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(return_value=_role_cfg(max_retries=2)),
    ):
        call = StructuredLLMCall(session=AsyncMock(), llm_client=llm)
        result = await call.invoke(
            role=SystemLLMRoleType.TRIAGE,
            payload={"user_message": "retry"},
            schema=_TriageOut,
        )

    assert result.value.type == "plan"
    assert llm.chat.await_count == 2


@pytest.mark.asyncio
async def test_structured_call_uses_fallback_when_validation_fails():
    llm = SimpleNamespace(chat=AsyncMock(return_value='{"unexpected":"shape"}'))
    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(return_value=_role_cfg(max_retries=0)),
    ):
        call = StructuredLLMCall(session=AsyncMock(), llm_client=llm)
        result = await call.invoke(
            role=SystemLLMRoleType.TRIAGE,
            payload={"user_message": "fallback"},
            schema=_TriageOut,
            fallback_factory=lambda _raw: _TriageOut(type="plan", confidence=0.0),
        )

    assert result.value.type == "plan"
    assert result.value.confidence == 0.0


@pytest.mark.asyncio
async def test_structured_call_raises_without_fallback():
    llm = SimpleNamespace(chat=AsyncMock(return_value="not-json"))
    with patch(
        "app.services.system_llm_role_service.SystemLLMRoleService.get_role_config",
        new=AsyncMock(return_value=_role_cfg(max_retries=0)),
    ):
        call = StructuredLLMCall(session=AsyncMock(), llm_client=llm)
        with pytest.raises(StructuredCallError):
            await call.invoke(
                role=SystemLLMRoleType.TRIAGE,
                payload={"user_message": "broken"},
                schema=_TriageOut,
            )
