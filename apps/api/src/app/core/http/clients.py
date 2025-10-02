from __future__ import annotations
from typing import Protocol, AsyncIterator, Mapping, Any, Optional
import httpx
from ..config import get_settings
from ..circuit_breaker import CircuitBreaker, CircuitBreakerConfig

class LLMClientProtocol(Protocol):
    async def chat(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, params: Optional[dict] = None) -> dict: ...
    async def chat_stream(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, params: Optional[dict] = None) -> AsyncIterator[str]: ...

class EmbClientProtocol(Protocol):
    async def embed_texts(self, texts: list[str], model: str = "default") -> list[list[float]]: ...
    async def embed_query(self, query: str, model: str = "default") -> list[float]: ...

class HTTPLLMClient:
    def __init__(self, base_url: str, *, timeout: int = 30, max_retries: int = 2, breaker: CircuitBreaker | None = None):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._retries = max_retries
        self._breaker = breaker

    async def chat(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, params: Optional[dict] = None) -> dict:
        payload = {"messages": messages}
        if model: payload["model"] = model
        if params: payload["params"] = params
        return await self._post_json("/chat", payload)

    async def chat_stream(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, params: Optional[dict] = None):
        payload = {"messages": messages}
        if model: payload["model"] = model
        if params: payload["params"] = params
        async with self._client.stream("POST", "/chat/stream", json=payload) as r:
            async for line in r.aiter_lines():
                if line:
                    yield line

    async def _post_json(self, path: str, payload: dict) -> dict:
        attempts = self._retries + 1
        for i in range(attempts):
            try:
                if self._breaker: self._breaker.before_call()
                resp = await self._client.post(path, json=payload)
                resp.raise_for_status()
                if self._breaker: self._breaker.on_success()
                return resp.json()
            except Exception:
                if self._breaker: self._breaker.on_failure()
                if i == attempts - 1: raise

    async def aclose(self):
        await self._client.aclose()

class HTTPEmbClient:
    def __init__(self, base_url: str, *, timeout: int = 30, max_retries: int = 2, breaker: CircuitBreaker | None = None):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._retries = max_retries
        self._breaker = breaker

    async def embed_texts(self, texts: list[str], model: str = "default") -> list[list[float]]:
        return await self._post_json("/embed/texts", {"texts": texts, "model": model})

    async def embed_query(self, query: str, model: str = "default") -> list[float]:
        data = await self._post_json("/embed/query", {"query": query, "model": model})
        return data.get("vector", [])

    async def _post_json(self, path: str, payload: dict) -> dict:
        attempts = self._retries + 1
        for i in range(attempts):
            try:
                if self._breaker: self._breaker.before_call()
                resp = await self._client.post(path, json=payload)
                resp.raise_for_status()
                if self._breaker: self._breaker.on_success()
                return resp.json()
            except Exception:
                if self._breaker: self._breaker.on_failure()
                if i == attempts - 1: raise

    async def aclose(self):
        await self._client.aclose()
