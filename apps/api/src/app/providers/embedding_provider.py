"""
Embedding Provider Interface and Implementations

Abstracts embedding generation from specific providers.
Allows easy swapping between OpenAI, Groq, local models, etc.
"""
from __future__ import annotations
from typing import Protocol, List
from abc import abstractmethod
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    """Interface for embedding providers
    
    All implementations must be OpenAI-compatible (for consistency).
    """
    
    @abstractmethod
    async def embed_texts(
        self,
        texts: List[str],
        model: str | None = None
    ) -> List[List[float]]:
        """Generate embeddings for texts
        
        Args:
            texts: List of text strings to embed
            model: Optional model override
            
        Returns:
            List of embedding vectors (list of floats)
        """
        ...


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider
    
    Uses OpenAI's /v1/embeddings endpoint.
    Can be used with OpenAI or any OpenAI-compatible API.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def embed_texts(
        self,
        texts: List[str],
        model: str | None = None
    ) -> List[List[float]]:
        """Generate embeddings via OpenAI API"""
        model_name = model or self.model
        
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            response = await self.client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json={
                    "input": texts,
                    "model": model_name
                }
            )
            response.raise_for_status()
            
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            
            logger.debug(
                f"[OpenAIEmbeddingProvider] Generated {len(embeddings)} embeddings "
                f"using {model_name}"
            )
            
            return embeddings
            
        except httpx.HTTPError as e:
            logger.error(f"[OpenAIEmbeddingProvider] HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"[OpenAIEmbeddingProvider] Error: {e}")
            raise
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


class LocalEmbeddingProvider:
    """Local embedding provider
    
    Connects to local embedding service (e.g. your current emb service).
    Expects OpenAI-compatible API.
    """
    
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def embed_texts(
        self,
        texts: List[str],
        model: str | None = None
    ) -> List[List[float]]:
        """Generate embeddings via local service"""
        model_name = model or self.model
        
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/embeddings",
                json={
                    "input": texts,
                    "model": model_name
                }
            )
            response.raise_for_status()
            
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            
            logger.debug(
                f"[LocalEmbeddingProvider] Generated {len(embeddings)} embeddings "
                f"using {model_name}"
            )
            
            return embeddings
            
        except httpx.HTTPError as e:
            logger.error(f"[LocalEmbeddingProvider] HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"[LocalEmbeddingProvider] Error: {e}")
            raise
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


def get_embedding_provider(
    provider: str,
    base_url: str,
    api_key: str | None,
    model: str,
    **kwargs
) -> EmbeddingProvider:
    """Factory function to create embedding provider
    
    Args:
        provider: Provider name (openai, local, groq, etc.)
        base_url: API base URL
        api_key: API key (if needed)
        model: Model name
        **kwargs: Additional provider-specific args
        
    Returns:
        EmbeddingProvider instance
    """
    if provider in ("openai", "groq", "azure"):
        return OpenAIEmbeddingProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            **kwargs
        )
    elif provider == "local":
        return LocalEmbeddingProvider(
            base_url=base_url,
            model=model,
            **kwargs
        )
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")
