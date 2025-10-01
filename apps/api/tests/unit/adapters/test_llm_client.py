
import asyncio
import pytest
from app.adapters.impl.llm_http import HttpLLMClient

@pytest.mark.asyncio
async def test_llm_client_smoke(monkeypatch):
    # Fake transport
    class DummyResp:
        def __init__(self, json):
            self.status_code = 200
            self._json = json
        def json(self): return self._json

    class DummyClient:
        def __init__(self, *a, **k): pass
        async def post(self, path, json):
            assert path in ("/chat",)
            assert "messages" in json
            return DummyResp({"content": "ok", "usage": {"tokens": 1}})
        async def stream(self, *a, **k):
            class Ctx:
                status_code = 200
                async def __aenter__(self): return self
                async def __aexit__(self, *e): return False
                async def aiter_lines(self):
                    for t in ["data: one", "data: two"]:
                        yield t
            return Ctx()
        async def aclose(self): pass

    monkeypatch.setattr("app.adapters.impl.llm_http.httpx.AsyncClient", DummyClient)
    cli = HttpLLMClient(base_url="http://dummy")
    r = await cli.chat([{"role":"user","content":"ping"}])
    assert r["content"] == "ok"
    chunks = []
    async for line in cli.chat_stream([{"role":"user","content":"ping"}]):
        chunks.append(line)
    assert chunks[-1] == "data: two"
    await cli.aclose()
