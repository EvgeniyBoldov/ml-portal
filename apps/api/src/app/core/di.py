from __future__ import annotations
from typing import Optional
from .http.clients import LLMClientProtocol
from .http.resolving_llm import ResolvingLLMClient
from ..adapters.impl.openai_compatible_llm import OpenAICompatibleLLM

_llm_client: Optional[LLMClientProtocol] = None

def get_llm_client() -> LLMClientProtocol:
    """
    Get LLM client instance.
    
    Uses OpenAI-compatible client for any provider that supports OpenAI API format.
    Supports: OpenAI, Groq, Azure OpenAI, LocalAI, vLLM, Ollama, etc.
    """
    global _llm_client
    if _llm_client is None:
        # Single runtime path: model connector resolution from DB.
        inner: LLMClientProtocol = OpenAICompatibleLLM()
        # Single choke-point: resolve slug → provider_model_name on every call.
        _llm_client = ResolvingLLMClient(inner)
    return _llm_client

def reset_llm_client() -> None:
    """Reset the global LLM client singleton.

    Must be called before each Celery task run because fork workers create a
    fresh event loop per task, and any cached AsyncOpenAI / httpx clients
    bound to the previous loop will raise "Future attached to a different loop".
    """
    global _llm_client
    if _llm_client is not None:
        inner = getattr(_llm_client, "_inner", None)
        if inner is not None and hasattr(inner, "clear_client_cache"):
            inner.clear_client_cache()
    _llm_client = None


async def cleanup_clients() -> None:
    global _llm_client
    if _llm_client is not None:
        await _llm_client.aclose()
        _llm_client = None
