
import asyncio
import pytest
from app.core.http.clients import HTTPLLMClient, HTTPEmbClient, ExternalServiceRateLimited
import httpx
from httpx import Response, Request

class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, responder):
        self._responder = responder
    async def handle_async_request(self, request: Request) -> Response:
        return await self._responder(request)

@pytest.mark.asyncio
async def test_llm_chat_success(monkeypatch):
    async def responder(req: Request) -> Response:
        assert req.url.path.endswith("/chat")
        return Response(200, json={"text":"ok","message":{"id":"1"}})
    transport = MockTransport(responder)
    client = HTTPLLMClient("http://llm", timeout=1, max_retries=0)
    client._client = httpx.AsyncClient(transport=transport)
    data = await client.chat([{"role":"user","content":"hi"}])
    assert "text" in data

@pytest.mark.asyncio
async def test_emb_embed_retry_and_cb(monkeypatch):
    calls = {"n":0}
    async def responder(req: Request) -> Response:
        calls["n"] += 1
        if calls["n"] < 2:
            # first call times out -> retry once
            raise httpx.TimeoutException("timeout")
        return Response(200, json={"embeddings":[[0.1,0.2,0.3]]})
    transport = MockTransport(responder)
    client = HTTPEmbClient("http://emb", timeout=1, max_retries=2)
    client._client = httpx.AsyncClient(transport=transport, timeout=1)
    vecs = await client.embed_texts(["a"])
    assert vecs and isinstance(vecs[0], list)

@pytest.mark.asyncio
async def test_rate_limited_raises(monkeypatch):
    async def responder(req: Request) -> Response:
        return Response(429, headers={"Retry-After":"5"}, json={"error":"rl"})
    transport = MockTransport(responder)
    client = HTTPLLMClient("http://llm", timeout=1, max_retries=0)
    client._client = httpx.AsyncClient(transport=transport)
    with pytest.raises(ExternalServiceRateLimited) as ei:
        await client.chat([{"role":"user","content":"hi"}])
    assert ei.value.retry_after == 5
