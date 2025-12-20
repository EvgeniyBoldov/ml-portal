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

    async def ensure_collection(self, name: str, dim: int, distance: str = "Cosine") -> None:
        """Create collection if it doesn't exist"""
        try:
            # Check if collection exists
            collections = await self._client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if name not in collection_names:
                # Create collection
                await self._client.create_collection(
                    collection_name=name,
                    vectors_config=qm.VectorParams(
                        size=dim,
                        distance=getattr(qm.Distance, distance.upper(), qm.Distance.COSINE)
                    )
                )
        except Exception as e:
            # If collection already exists, that's fine
            if "already exists" not in str(e).lower():
                raise

    async def upsert(self, collection: str, vectors: Sequence[Sequence[float]], payloads: Sequence[Mapping[str, Any]], ids: Sequence[str] | None = None) -> None:
        points = []
        for i, vec in enumerate(vectors):
            pid = (ids[i] if ids else None) or str(i)
            points.append(qm.PointStruct(id=pid, vector=list(vec), payload=dict(payloads[i])))
        await self._client.upsert(collection_name=collection, points=points)

    async def search(self, collection: str, query: Sequence[float], top_k: int = 5, filter: Mapping[str, Any] | qm.Filter | None = None) -> list[dict]:
        """Search vectors using query_points (qdrant-client >= 1.7.0)"""
        query_filter = _dict_to_filter(filter) if not isinstance(filter, qm.Filter) else filter
        
        # Use query_points instead of deprecated search method
        response = await self._client.query_points(
            collection_name=collection,
            query=list(query),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        
        # Convert ScoredPoint objects to dicts
        return [
            {
                "id": point.id,
                "score": point.score,
                "payload": point.payload or {},
            }
            for point in response.points
        ]

    async def collection_exists(self, name: str) -> bool:
        """Check if collection exists in Qdrant"""
        try:
            collections = await self._client.get_collections()
            return name in [c.name for c in collections.collections]
        except Exception:
            return False
