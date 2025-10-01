from __future__ import annotations

from typing import Protocol, Sequence, Mapping, Any, Optional, AsyncIterator
import httpx
import asyncio

from app.adapters.exceptions.base import UpstreamError
from app.core.logging import get_logger
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = get_logger(__name__)

# ---------- Protocols ----------

class LLMClientProtocol(Protocol):
    async def chat(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, **params) -> dict: ...
    async def chat_stream(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, **params) -> AsyncIterator[str]: ...
    async def aclose(self) -> None: ...

class EmbClientProtocol(Protocol):
    async def embed_texts(self, texts: Sequence[str], *, model: str = "default") -> list[list[float]]: ...
    async def embed_query(self, query: str, *, model: str = "default") -> list[float]: ...
    async def aclose(self) -> None: ...

# ---------- HTTP helpers ----------

def _mk_client(base_url: str, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=timeout,
        headers={"User-Agent": "ml-portal/clients"}
    )

async def _request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int,
    json: Any | None = None,
    stream: bool = False,
) -> httpx.Response | httpx.AsyncByteStream:
    backoff = 0.25
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            if stream:
                # NOTE: return the context manager directly; do not await it here.
                return client.stream(method, url, json=json)
            return await client.request(method, url, json=json)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt >= max_retries:
                break
            # Do NOT close the shared AsyncClient here; just back off and retry.
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 2.0)
        except Exception as e:
            raise e

    assert last_exc is not None
    raise UpstreamError(f"HTTP request failed after {max_retries} retries: {last_exc}")

# ---------- LLM HTTP client ----------

class HTTPLLMClient(LLMClientProtocol):
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._client = _mk_client(base_url, timeout)
        self._max_retries = max_retries
        self._breaker = breaker or CircuitBreaker("llm", CircuitBreakerConfig())

    async def chat(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, **params) -> dict:
        self._breaker.before_call()
        payload = {"messages": messages, "params": {**params}}
        if model is not None:
            payload["params"]["model"] = model
        try:
            resp = await _request_with_retries(
                self._client, "POST", "/chat", max_retries=self._max_retries, json=payload
            )
            if resp.status_code >= 400:
                raise UpstreamError(f"LLM error: {resp.status_code} {resp.text}")
            data = resp.json()
            self._breaker.on_success()
            return data
        except Exception as e:
            self._breaker.on_failure()
            logger.error("LLM.chat failed", extra={"error": str(e)})
            raise

    async def chat_stream(self, messages: list[Mapping[str, str]], *, model: Optional[str] = None, **params) -> AsyncIterator[str]:
        self._breaker.before_call()
        payload = {"messages": messages, "params": {**params}}
        if model is not None:
            payload["params"]["model"] = model

        try:
            async with _request_with_retries(  # <-- no await here
                self._client, "POST", "/chat/stream", max_retries=self._max_retries, json=payload, stream=True
            ) as r:
                if r.status_code >= 400:
                    text = await r.aread()
                    raise UpstreamError(f"LLM stream error: {r.status_code} {text.decode('utf-8', 'ignore')}")
                async for chunk in r.aiter_text():
                    if chunk:
                        yield chunk
            self._breaker.on_success()
        except Exception as e:
            self._breaker.on_failure()
            logger.error("LLM.chat_stream failed", extra={"error": str(e)})
            raise

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        finally:
            pass

# ---------- Embeddings HTTP client ----------

class HTTPEmbClient(EmbClientProtocol):
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._client = _mk_client(base_url, timeout)
        self._max_retries = max_retries
        self._breaker = breaker or CircuitBreaker("emb", CircuitBreakerConfig())

    async def embed_texts(self, texts: Sequence[str], *, model: str = "default") -> list[list[float]]:
        self._breaker.before_call()
        try:
            resp = await _request_with_retries(
                self._client, "POST", "/embed", max_retries=self._max_retries, json={"texts": list(texts), "model": model}
            )
            if resp.status_code >= 400:
                raise UpstreamError(f"Embeddings error: {resp.status_code} {resp.text}")
            data = resp.json()
            self._breaker.on_success()
            return data["embeddings"]
        except Exception as e:
            self._breaker.on_failure()
            logger.error("Embeddings.embed_texts failed", extra={"error": str(e)})
            raise

    async def embed_query(self, query: str, *, model: str = "default") -> list[float]:
        [vec] = await self.embed_texts([query], model=model)
        return vec

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        finally:
            pass
