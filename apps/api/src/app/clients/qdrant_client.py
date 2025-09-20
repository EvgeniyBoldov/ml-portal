# PATCHED: align with emb_client.EMBClient and handle single-text embedding safely.
# Replace the whole file with this version if your file previously imported `EmbeddingsClient`.

from __future__ import annotations

from typing import List, Optional, Any
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from app.clients.emb_client import EMBClient  # our concrete embedder
from app.core.settings import Settings

settings = Settings()

class QdrantSearchResult(BaseModel):
    id: str
    score: float
    payload: dict

class QdrantVectorStore:
    def __init__(
        self,
        collection: str,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        prefer_grpc: bool = False,
        client: Optional[QdrantClient] = None,
        embedder: Optional[EMBClient] = None,
        vector_size: Optional[int] = None,
        distance: str = "Cosine",
    ) -> None:
        self.collection = collection
        self.client = client or QdrantClient(url=url or settings.QDRANT_URL, api_key=api_key or settings.QDRANT_API_KEY, prefer_grpc=prefer_grpc)
        self.embedder = embedder or EMBClient()
        # Infer dimension if not provided by doing a tiny dummy embed
        self.vector_size = vector_size
        self.distance = distance

        if self.vector_size is None:
            probe = self.embedder.embed(["__probe__"])
            if not probe or not probe[0]:
                raise RuntimeError("Embedder returned empty vector; cannot infer dimension")
            self.vector_size = len(probe[0])

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        exists = False
        try:
            info = self.client.get_collection(self.collection)
            exists = info is not None
        except Exception:
            exists = False

        if not exists:
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=getattr(Distance, self.distance),
                ),
            )

    # Helper: embed a single string via our batch embedder
    def _embed_one(self, text: str) -> List[float]:
        vecs = self.embedder.embed([text])
        if not vecs or not vecs[0]:
            raise RuntimeError("Failed to embed text (empty vector)")
        return vecs[0]

    def index(self, ids: List[str], contents: List[str], payloads: Optional[List[dict]] = None) -> None:
        if payloads and len(payloads) != len(ids):
            raise ValueError("payloads length must match ids")
        vectors = self.embedder.embed(contents)
        points = []
        for i, vid in enumerate(ids):
            pl = payloads[i] if payloads else {}
            points.append(
                PointStruct(
                    id=vid,
                    vector=vectors[i],
                    payload=pl,
                )
            )
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query: str, top_k: int = 5, filter_by: Optional[dict] = None) -> List[QdrantSearchResult]:
        vector = self._embed_one(query)
        qfilter = None
        if filter_by:
            conditions = []
            for k, v in filter_by.items():
                conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
            qfilter = Filter(must=conditions)
        results = self.client.search(collection_name=self.collection, query_vector=vector, limit=top_k, query_filter=qfilter)
        return [QdrantSearchResult(id=str(r.id), score=r.score, payload=r.payload or {}) for r in results]

    def delete_by_id(self, ids: List[str]) -> None:
        self.client.delete(collection_name=self.collection, points_selector=ids)

    def delete_by_filter(self, filter_by: dict) -> None:
        conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filter_by.items()]
        self.client.delete(collection_name=self.collection, points_selector=Filter(must=conditions))
