import pytest

from app.adapters.impl.qdrant import QdrantVectorStore

class DummyAsyncQdrant:
    def __init__(self, *a, **k): self.calls = []
    async def upsert(self, collection_name, points): self.calls.append(("upsert", collection_name, points))
    async def search(self, collection_name, query_vector, limit, query_filter):
        # emulate qdrant response .dict()
        class R:
            def __init__(self, i): self._i=i
            def dict(self): return {"id": str(self._i), "score": 0.95}
        return [R(1), R(2)]

@pytest.mark.anyio
async def test_upsert_and_search(monkeypatch):
    import app.adapters.impl.qdrant as mod
    monkeypatch.setattr(mod, "AsyncQdrantClient", DummyAsyncQdrant)

    vs = QdrantVectorStore(url="http://q:6333", timeout=1.0)
    await vs.upsert("docs", [[0.1,0.2],[0.3,0.4]], [{"k":"v1"},{"k":"v2"}], ids=["a","b"])
    res = await vs.search("docs", [0.1,0.2], top_k=2, filter={"must": [["tenant_id","t1"]]})
    assert len(res) == 2 and res[0]["id"] == "1"
