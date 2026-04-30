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
        s = get_settings()
        # Single runtime path: model connector resolution from DB.
        inner: LLMClientProtocol = OpenAICompatibleLLM()
        # Single choke-point: resolve slug → provider_model_name on every call.
        _llm_client = ResolvingLLMClient(inner)
    return _llm_client

async def cleanup_clients() -> None:
    global _llm_client
    if _llm_client is not None:
        await _llm_client.aclose()
        _llm_client = None
