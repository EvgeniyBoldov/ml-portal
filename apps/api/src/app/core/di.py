
from __future__ import annotations
from typing import Optional
from .config import settings
from .http.clients import HTTPLLMClient as _HTTPLLMClient, HTTPEmbClient as _HTTPEmbClient, LLMClientProtocol, EmbClientProtocol
from .circuit_breaker import CircuitBreaker, CircuitBreakerState

_llm_client: Optional[_HTTPLLMClient] = None
_emb_client: Optional[_HTTPEmbClient] = None

# Re-export classes with canonical names
HTTPLLMClient = _HTTPLLMClient
HTTPEmbClient = _HTTPEmbClient

def get_llm_client() -> LLMClientProtocol:
    global _llm_client
    if _llm_client is None:
        _llm_client = HTTPLLMClient(settings.LLM_BASE_URL, timeout=settings.HTTP_TIMEOUT_SECONDS, max_retries=settings.HTTP_MAX_RETRIES)
    return _llm_client

def get_emb_client() -> EmbClientProtocol:
    global _emb_client
    if _emb_client is None:
        _emb_client = HTTPEmbClient(settings.EMB_BASE_URL, timeout=settings.HTTP_TIMEOUT_SECONDS, max_retries=settings.HTTP_MAX_RETRIES)
    return _emb_client

async def cleanup_clients() -> None:
    global _llm_client, _emb_client
    if _llm_client is not None:
        await _llm_client.aclose()
        _llm_client = None
    if _emb_client is not None:
        await _emb_client.aclose()
        _emb_client = None
