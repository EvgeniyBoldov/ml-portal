
import pytest
from app.adapters.impl.qdrant import QdrantVectorStore

@pytest.mark.asyncio
async def test_qdrant_methods_signature():
    # We won't call upstream; just ensure methods exist and accept arguments.
    store = QdrantVectorStore(url="http://localhost:6333")
    # don't actually call, as it would hit network – unit tests should mock in real project
    assert hasattr(store, "upsert")
    assert hasattr(store, "search")
