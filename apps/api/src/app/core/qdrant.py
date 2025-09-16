from __future__ import annotations
from qdrant_client import QdrantClient
from .config import settings

_client: QdrantClient | None = None

def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.QDRANT_URL, prefer_grpc=False)
    return _client
