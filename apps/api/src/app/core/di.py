from __future__ import annotations
from typing import Optional
from .config import get_settings
from .http.clients import HTTPLLMClient as _HTTPLLMClient, HTTPEmbClient as _HTTPEmbClient, LLMClientProtocol, EmbClientProtocol
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig

_llm_client: Optional[_HTTPLLMClient] = None
_emb_client: Optional[_HTTPEmbClient] = None

HTTPLLMClient = _HTTPLLMClient
HTTPEmbClient = _HTTPEmbClient

def get_llm_client() -> LLMClientProtocol:
    global _llm_client
    if _llm_client is None:
        s = get_settings()
        breaker_config = CircuitBreakerConfig(
            failures_threshold=s.CB_LLM_FAILURES_THRESHOLD,
            open_timeout_seconds=s.CB_LLM_OPEN_TIMEOUT_SECONDS,
            half_open_max_calls=s.CB_LLM_HALF_OPEN_MAX_CALLS
        )
        _llm_client = HTTPLLMClient(s.LLM_BASE_URL, timeout=s.HTTP_TIMEOUT_SECONDS, max_retries=s.HTTP_MAX_RETRIES, breaker=CircuitBreaker("llm", breaker_config))
    return _llm_client

def get_emb_client() -> EmbClientProtocol:
    global _emb_client
    if _emb_client is None:
        s = get_settings()
        breaker_config = CircuitBreakerConfig(
            failures_threshold=s.CB_EMB_FAILURES_THRESHOLD,
            open_timeout_seconds=s.CB_EMB_OPEN_TIMEOUT_SECONDS,
            half_open_max_calls=s.CB_EMB_HALF_OPEN_MAX_CALLS
        )
        _emb_client = HTTPEmbClient(s.EMB_BASE_URL, timeout=s.HTTP_TIMEOUT_SECONDS, max_retries=s.HTTP_MAX_RETRIES, breaker=CircuitBreaker("emb", breaker_config))
    return _emb_client

async def cleanup_clients() -> None:
    global _llm_client, _emb_client
    if _llm_client is not None:
        await _llm_client.aclose()
        _llm_client = None
    if _emb_client is not None:
        await _emb_client.aclose()
        _emb_client = None
