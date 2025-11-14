from __future__ import annotations
from typing import Protocol, Sequence, Mapping, Any

class VectorStore(Protocol):
    async def upsert(
        self,
        collection: str,
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[Mapping[str, Any]],
        ids: Sequence[str] | None = None,
    ) -> None: ...
    async def search(
        self,
        collection: str,
        query: Sequence[float],
        top_k: int = 5,
        filter: Mapping[str, Any] | None = None,
    ) -> list[dict]: ...
