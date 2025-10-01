from __future__ import annotations
from typing import Sequence, Mapping, Any
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm
from app.core.config import get_settings

def _dict_to_filter(f: Mapping[str, Any] | None) -> qm.Filter | None:
    if f is None:
        return None
    if isinstance(f, qm.Filter):
        return f
    def _pairs(obj):
        if isinstance(obj, dict):
            return list(obj.items())
        return list(obj or [])
    must = [qm.FieldCondition(key=k, match=qm.MatchValue(value=v)) for k, v in _pairs(f.get("must"))] if isinstance(f, dict) else []
    should = [qm.FieldCondition(key=k, match=qm.MatchValue(value=v)) for k, v in _pairs(f.get("should"))] if isinstance(f, dict) else []
    must_not = [qm.FieldCondition(key=k, match=qm.MatchValue(value=v)) for k, v in _pairs(f.get("must_not"))] if isinstance(f, dict) else []
    if not any([must, should, must_not]):
        if isinstance(f, dict):
            must = [qm.FieldCondition(key=k, match=qm.MatchValue(value=v)) for k, v in f.items()]
    return qm.Filter(must=must or None, should=should or None, must_not=must_not or None)

class QdrantVectorStore:
    def __init__(self, url: str | None = None, timeout: float | None = None):
        s = get_settings()
        self._client = AsyncQdrantClient(url or s.QDRANT_URL, timeout=timeout or s.TIMEOUT_SECONDS)

    async def upsert(self, collection: str, vectors: Sequence[Sequence[float]], payloads: Sequence[Mapping[str, Any]], ids: Sequence[str] | None = None) -> None:
        points = []
        for i, vec in enumerate(vectors):
            pid = (ids[i] if ids else None) or str(i)
            points.append(qm.PointStruct(id=pid, vector=list(vec), payload=dict(payloads[i])))
        await self._client.upsert(collection_name=collection, points=points)

    async def search(self, collection: str, query: Sequence[float], top_k: int = 5, filter: Mapping[str, Any] | qm.Filter | None = None) -> list[dict]:
        rr = await self._client.search(collection_name=collection, query_vector=list(query), limit=top_k, query_filter=_dict_to_filter(filter) if not isinstance(filter, qm.Filter) else filter)
        return [r.dict() for r in rr]
