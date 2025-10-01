from typing import Sequence, Mapping, Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm
from ..interfaces.vector_store import VectorStore
from ...core.config import get_settings

class QdrantVectorStore(VectorStore):
    def __init__(self, url: Optional[str] = None, timeout: Optional[float] = None):
        s = get_settings()
        self._client = AsyncQdrantClient(url or s.QDRANT_URL, timeout=timeout or s.HTTP_TIMEOUT_SECONDS)

    async def upsert(self, collection: str, points: Sequence[Mapping[str, Any]]) -> None:
        await self._client.upsert(
            collection_name=collection,
            points=[qm.PointStruct(id=p["id"], vector=p["vector"], payload=p.get("payload")) for p in points],
        )

    async def query(self, collection: str, vector: Sequence[float], top_k: int = 5) -> list[Mapping[str, Any]]:
        res = await self._client.search(collection_name=collection, query_vector=vector, limit=top_k)
        return [r.dict() for r in res]

    async def aclose(self) -> None:
        await self._client.close()
