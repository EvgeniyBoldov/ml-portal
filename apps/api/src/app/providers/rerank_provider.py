"""
Rerank Provider Interface and Implementations

Reranking improves search results by re-scoring candidates
based on semantic relevance to the query.
"""
from __future__ import annotations
from typing import Protocol, List, Dict, Any
from abc import abstractmethod
from dataclasses import dataclass
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RankedDocument:
    """Reranked document with score"""
    index: int  # Original index in input list
    text: str
    score: float
    relevance_score: float | None = None  # Normalized 0-1 score


class RerankProvider(Protocol):
    """Interface for reranking providers"""
    
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int | None = None
    ) -> List[RankedDocument]:
        """Rerank documents by relevance to query
        
        Args:
            query: Search query
            documents: List of candidate documents
            top_k: Return only top K results (None = all)
            
        Returns:
            List of RankedDocument sorted by relevance (best first)
        """
        ...


class LocalRerankProvider:
    """Local reranker service
    
    Connects to local cross-encoder reranker container.
    Expected API format (OpenAI-style):
    
    POST /v1/rerank
    {
      "query": "...",
      "documents": ["...", "..."],
      "top_k": 10
    }
    
    Response:
    {
      "results": [
        {"index": 0, "score": 0.95, "text": "..."},
        ...
      ]
    }
    """
    
    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int | None = None
    ) -> List[RankedDocument]:
        """Rerank documents via local service"""
        if not documents:
            return []
        
        try:
            payload: Dict[str, Any] = {
                "query": query,
                "documents": documents
            }
            
            if top_k is not None:
                payload["top_k"] = top_k
            
            if self.model:
                payload["model"] = self.model
            
            response = await self.client.post(
                f"{self.base_url}/v1/rerank",
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            ranked = [
                RankedDocument(
                    index=item["index"],
                    text=item.get("text", documents[item["index"]]),
                    score=item["score"],
                    relevance_score=item.get("relevance_score")
                )
                for item in results
            ]
            
            logger.debug(
                f"[LocalRerankProvider] Reranked {len(documents)} docs, "
                f"returned top {len(ranked)}"
            )
            
            return ranked
            
        except httpx.HTTPError as e:
            logger.error(f"[LocalRerankProvider] HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"[LocalRerankProvider] Error: {e}")
            raise
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


class CohereRerankProvider:
    """Cohere Rerank API provider
    
    Uses Cohere's rerank-english-v2.0 or similar models.
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "rerank-english-v3.0",
        timeout: int = 30
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int | None = None
    ) -> List[RankedDocument]:
        """Rerank documents via Cohere API"""
        if not documents:
            return []
        
        try:
            payload: Dict[str, Any] = {
                "query": query,
                "documents": documents,
                "model": self.model,
                "return_documents": False  # We already have them
            }
            
            if top_k is not None:
                payload["top_n"] = top_k
            
            response = await self.client.post(
                "https://api.cohere.ai/v1/rerank",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            ranked = [
                RankedDocument(
                    index=item["index"],
                    text=documents[item["index"]],
                    score=item["relevance_score"],
                    relevance_score=item["relevance_score"]
                )
                for item in results
            ]
            
            logger.debug(
                f"[CohereRerankProvider] Reranked {len(documents)} docs, "
                f"returned top {len(ranked)}"
            )
            
            return ranked
            
        except httpx.HTTPError as e:
            logger.error(f"[CohereRerankProvider] HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"[CohereRerankProvider] Error: {e}")
            raise
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


def get_rerank_provider(provider: str, **kwargs) -> RerankProvider:
    """Factory function to create rerank provider
    
    Args:
        provider: Provider name (local, cohere, voyage, jina)
        **kwargs: Provider-specific args
        
    Returns:
        RerankProvider instance
    """
    if provider == "local":
        return LocalRerankProvider(**kwargs)
    elif provider == "cohere":
        return CohereRerankProvider(**kwargs)
    else:
        raise ValueError(f"Unknown rerank provider: {provider}")
