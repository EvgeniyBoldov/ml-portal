from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.agents.operation_router import DirectOperationExecutor


@pytest.mark.asyncio
async def test_post_with_retry_retries_on_retryable_http_status():
    executor = DirectOperationExecutor()
    executor._http_max_retries = 2
    executor._retry_base_delay_ms = 1

    first = httpx.Response(503, request=httpx.Request("POST", "http://provider"))
    second = httpx.Response(200, request=httpx.Request("POST", "http://provider"), text='{"ok":true}')
    client = AsyncMock()
    client.post = AsyncMock(side_effect=[first, second])

    response, attempts = await executor._post_with_retry(
        client=client,
        provider_url="http://provider",
        headers={},
        payload={"a": 1},
        timeout_s=30,
    )

    assert response.status_code == 200
    assert attempts == 2
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_post_with_retry_retries_on_connect_error():
    executor = DirectOperationExecutor()
    executor._http_max_retries = 2
    executor._retry_base_delay_ms = 1

    second = httpx.Response(200, request=httpx.Request("POST", "http://provider"), text='{"ok":true}')
    client = AsyncMock()
    client.post = AsyncMock(side_effect=[httpx.ConnectError("boom"), second])

    response, attempts = await executor._post_with_retry(
        client=client,
        provider_url="http://provider",
        headers={},
        payload={"a": 1},
        timeout_s=30,
    )

    assert response.status_code == 200
    assert attempts == 2
    assert client.post.await_count == 2


def test_retryable_status_and_exception_contract():
    executor = DirectOperationExecutor()

    assert executor._is_retryable_status(503) is True
    assert executor._is_retryable_status(400) is False

    assert executor._is_retryable_exception(httpx.ConnectError("x")) is True
    assert executor._is_retryable_exception(ValueError("x")) is False
