from __future__ import annotations
import asyncio
from typing import Sequence, Mapping, Any
import httpx
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.http import models as qm
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _is_not_found_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "404" in msg or "not found" in msg


def _is_query_endpoint_unsupported(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        ("404" in msg and "/points/query" in msg)
        or "unknown endpoint" in msg
        or "method not allowed" in msg
    )


def _should_try_legacy_search(exc: Exception) -> bool:
    # Qdrant < 1.10 may return plain 404 for /points/query with no endpoint hint.
    return _is_query_endpoint_unsupported(exc) or _is_not_found_error(exc)

def _match_condition(key: str, value: Any) -> qm.FieldCondition:
    if isinstance(value, (list, tuple, set)):
        return qm.FieldCondition(key=key, match=qm.MatchAny(any=list(value)))
    return qm.FieldCondition(key=key, match=qm.MatchValue(value=value))

def _dict_to_filter(f: Mapping[str, Any] | None) -> qm.Filter | None:
    if f is None:
        return None
    if isinstance(f, qm.Filter):
        return f
    def _pairs(obj):
        if isinstance(obj, dict):
            return list(obj.items())
        return list(obj or [])
    must = [_match_condition(k, v) for k, v in _pairs(f.get("must"))] if isinstance(f, dict) else []
    should = [_match_condition(k, v) for k, v in _pairs(f.get("should"))] if isinstance(f, dict) else []
    must_not = [_match_condition(k, v) for k, v in _pairs(f.get("must_not"))] if isinstance(f, dict) else []
    if not any([must, should, must_not]):
        if isinstance(f, dict):
            must = [_match_condition(k, v) for k, v in f.items()]
    return qm.Filter(must=must or None, should=should or None, must_not=must_not or None)

class QdrantVectorStore:
    def __init__(self, url: str | None = None, timeout: float | None = None):
        s = get_settings()
        base_url = url or s.QDRANT_URL
        timeout_value = timeout or s.TIMEOUT_SECONDS
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_value
        self._client = AsyncQdrantClient(base_url, timeout=timeout_value)
        # Keep sync client for compatibility paths where available.
        self._sync_client = QdrantClient(base_url, timeout=timeout_value)

    async def _legacy_search(
        self,
        collection: str,
        query: Sequence[float],
        top_k: int,
        query_filter: qm.Filter | None,
    ) -> list[dict]:
        # Prefer client method when available.
        sync_search = getattr(self._sync_client, "search", None)
        if sync_search is not None:
            points = await asyncio.to_thread(
                sync_search,
                collection_name=collection,
                query_vector=list(query),
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
            return [
                {"id": point.id, "score": point.score, "payload": point.payload or {}}
                for point in (points or [])
            ]

        # Fallback to direct REST for older server API: /points/search
        filter_payload = query_filter.model_dump(exclude_none=True) if query_filter else None
        payload: dict[str, Any] = {
            "vector": list(query),
            "limit": top_k,
            "with_payload": True,
        }
        if filter_payload:
            payload["filter"] = filter_payload
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/collections/{collection}/points/search",
                json=payload,
            )
        if resp.status_code == 404:
            raise RuntimeError("404 Not Found")
        resp.raise_for_status()
        body = resp.json() or {}
        result = body.get("result") or []
        return [
            {
                "id": point.get("id"),
                "score": point.get("score"),
                "payload": point.get("payload") or {},
            }
            for point in result
        ]

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
                return

            info = await self._client.get_collection(collection_name=name)
            vectors_cfg = getattr(getattr(info, "config", None), "params", None)
            vectors = getattr(vectors_cfg, "vectors", None) if vectors_cfg is not None else None
            actual_dim = None
            if hasattr(vectors, "size"):
                actual_dim = int(vectors.size)
            elif isinstance(vectors, dict):
                # named vectors case: use first declared vector size
                for _, cfg in vectors.items():
                    size = getattr(cfg, "size", None)
                    if size is not None:
                        actual_dim = int(size)
                        break
            if actual_dim is not None and actual_dim != int(dim):
                raise ValueError(
                    f"Qdrant collection '{name}' has vector dim {actual_dim}, expected {dim}"
                )
        except Exception as e:
            # If collection already exists, that's fine
            if "already exists" not in str(e).lower():
                raise

    async def get_client(self) -> AsyncQdrantClient:
        """Expose underlying async client for advanced operations."""
        return self._client

    async def upsert(self, collection: str, vectors: Sequence[Sequence[float]], payloads: Sequence[Mapping[str, Any]], ids: Sequence[str] | None = None) -> None:
        points = []
        for i, vec in enumerate(vectors):
            pid = (ids[i] if ids else None) or str(i)
            points.append(qm.PointStruct(id=pid, vector=list(vec), payload=dict(payloads[i])))
        await self._client.upsert(collection_name=collection, points=points)

    async def search(
        self,
        collection: str,
        query: Sequence[float],
        top_k: int = 5,
        filter: Mapping[str, Any] | qm.Filter | None = None,
    ) -> list[dict]:
        """
        Search vectors via async query API.

        Primary path uses `query_points` (supported by current async client).
        If collection was concurrently removed and backend returns 404, return [].
        """
        query_filter = _dict_to_filter(filter) if not isinstance(filter, qm.Filter) else filter
        try:
            response = await self._client.query_points(
                collection_name=collection,
                query=list(query),
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
            points = getattr(response, "points", response) or []
            return [
                {
                    "id": point.id,
                    "score": point.score,
                    "payload": point.payload or {},
                }
                for point in points
            ]
        except Exception as exc:
            if _should_try_legacy_search(exc):
                logger.info("Qdrant query_points failed, fallback to legacy search for %s", collection)
                try:
                    return await self._legacy_search(
                        collection=collection,
                        query=query,
                        top_k=top_k,
                        query_filter=query_filter,
                    )
                except Exception as legacy_exc:
                    if _is_not_found_error(legacy_exc):
                        logger.warning("Qdrant collection not found during legacy search: %s", collection)
                        return []
                    raise
            raise

    async def delete_by_filter(self, collection: str, filter: Mapping[str, Any] | qm.Filter) -> None:
        query_filter = _dict_to_filter(filter) if not isinstance(filter, qm.Filter) else filter
        if query_filter is None:
            return
        await self._client.delete(
            collection_name=collection,
            points_selector=qm.FilterSelector(filter=query_filter),
        )

    async def delete_collection(self, name: str) -> None:
        await self._client.delete_collection(collection_name=name)

    async def collection_exists(self, name: str) -> bool:
        """Check if collection exists in Qdrant"""
        try:
            collections = await self._client.get_collections()
            return name in [c.name for c in collections.collections]
        except Exception:
            return False
