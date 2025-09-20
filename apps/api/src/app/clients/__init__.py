"""
HTTP клиенты для внешних сервисов
"""
from .emb_client import emb_client, EMBClient
from .llm_client import llm_client, LLMClient
from app.core.qdrant import get_qdrant

# Создаем экземпляры для тестов
_emb_client = emb_client
_llm_client = llm_client
_qdrant = get_qdrant()

async def embed_texts_async(texts, model="minilm"):
    """Async embedding function"""
    return await emb_client.embed(texts, model=model)

def embed_texts(texts, model="minilm"):
    """Sync embedding function"""
    import asyncio
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(embed_texts_async(texts, model))

def get_llm():
    """Get LLM client instance"""
    return _llm_client

def get_qdrant():
    """Get Qdrant client instance"""
    return _qdrant

__all__ = ["emb_client", "EMBClient", "llm_client", "LLMClient", "get_qdrant", "embed_texts", "embed_texts_async", "get_llm"]
