import pytest
from app.adapters.impl.qdrant import QdrantVectorStore

class DummyAsyncQdrant:
    def __init__(self, *a, **k): self.calls = []
    async def upsert(self, collection_name, points): self.calls.append(("upsert", collection_name, points))
    async def search(self, collection_name, query_vector, limit, query_filter): 
        return [type("R", (), {"dict": lambda self: {"id": "1", "score": 0.9}})()]

@pytest.mark.anyio
async def test_qdrant_upsert_search(monkeypatch):
    import app.adapters.impl.qdrant as mod
    monkeypatch.setattr(mod, "AsyncQdrantClient", DummyAsyncQdrant)

    vs = QdrantVectorStore(url="http://qdrant:6333", timeout=1.0)
    await vs.upsert("docs", [[0.1,0.2]], [{"k": "v"}], ids=["42"])
    res = await vs.search("docs", [0.1,0.2], top_k=1, filter=None)

    assert res and res[0]["id"] == "1"
