from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.impl.openai_compatible_llm import OpenAICompatibleLLM


@pytest.mark.asyncio
async def test_aclose_ignores_event_loop_shutdown_errors():
    client = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("Event loop is closed")))
    llm = object.__new__(OpenAICompatibleLLM)
    llm._client_cache = {("http://example", None): client}

    await OpenAICompatibleLLM.aclose(llm)

    assert llm._client_cache == {}
    assert client.close.await_count == 1
