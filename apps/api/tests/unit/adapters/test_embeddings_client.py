
import pytest
from app.adapters.impl.emb_http import HttpEmbeddingsClient

@pytest.mark.asyncio
async def test_embeddings_client(monkeypatch):
    class DummyResp:
        status_code = 200
        def __init__(self): self._json = {"embeddings": [[0.1, 0.2]]}
        def json(self): return self._json

    class DummyClient:
        def __init__(self,*a,**k): pass
        async def post(self, path, json): return DummyResp()
        async def aclose(self): pass

    monkeypatch.setattr("app.adapters.impl.emb_http.httpx.AsyncClient", DummyClient)
    cli = HttpEmbeddingsClient(base_url="http://dummy")
    vecs = await cli.embed(["hi"])
    assert vecs and isinstance(vecs[0][0], float)
    await cli.aclose()
