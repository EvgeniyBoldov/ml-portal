from typing import Sequence, Optional
import httpx
from ..exceptions.base import UpstreamError
from ..interfaces.embeddings import EmbeddingsClient
from ..utils.http import new_async_http_client
from ...core.config import get_settings

class HttpEmbeddingsClient(EmbeddingsClient):
    def __init__(self, base_url: Optional[str] = None):
        s = get_settings()
        self._base = (base_url or s.EMB_BASE_URL).rstrip("/")
        self._client: httpx.AsyncClient = new_async_http_client(self._base)

    async def embed_texts(self, texts: Sequence[str], model: str = "default") -> list[list[float]]:
        resp = await self._client.post("/embed", json={"texts": list(texts), "model": model})
        if resp.status_code >= 400:
            raise UpstreamError(f"Embeddings error: {resp.status_code} {resp.text}")
        data = resp.json()
        return data["embeddings"]

    async def embed_query(self, query: str, model: str = "default") -> list[float]:
        [vec] = await self.embed_texts([query], model=model)
        return vec

    async def aclose(self) -> None:
        await self._client.aclose()
