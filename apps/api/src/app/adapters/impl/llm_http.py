from typing import AsyncIterator, Mapping, Optional
import httpx
from ..exceptions.base import UpstreamError
from ..interfaces.llm import LLMClient
from ..utils.http import new_async_http_client
from ...core.config import get_settings

class HttpLLMClient(LLMClient):
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        s = get_settings()
        self._base = (base_url or s.LLM_BASE_URL).rstrip("/")
        self._client: httpx.AsyncClient = new_async_http_client(self._base)

    async def chat(self, messages: list[Mapping[str, str]], *, params: Optional[dict] = None) -> dict:
        resp = await self._client.post("/chat", json={"messages": messages, "params": params or {}})
        if resp.status_code >= 400:
            raise UpstreamError(f"LLM error: {resp.status_code} {resp.text}")
        return resp.json()

    async def chat_stream(self, messages: list[Mapping[str, str]], *, params: Optional[dict] = None) -> AsyncIterator[str]:
        async with self._client.stream("POST", "/chat/stream", json={"messages": messages, "params": params or {}}) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise UpstreamError(f"LLM stream error: {resp.status_code} {body!r}")
            async for line in resp.aiter_lines():
                if line:
                    yield line

    async def aclose(self) -> None:
        await self._client.aclose()
