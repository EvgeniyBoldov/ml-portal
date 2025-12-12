"""Model Health Checker Service

Performs health checks for different model providers:
- OpenAI-compatible APIs (OpenAI, Groq, Azure, local vLLM/Ollama)
- Local embedding services (HTTP API)
- HuggingFace local models

Health check strategy:
1. For LLM: Send minimal completion request
2. For Embedding: Send minimal embed request
3. Measure latency and check response validity
"""
from __future__ import annotations
import asyncio
import time
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import os
import httpx

from app.models.model_registry import Model, ModelType, HealthStatus
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    status: HealthStatus
    latency_ms: int
    error: Optional[str] = None
    details: Optional[dict] = None


class ModelHealthChecker:
    """Service for checking model availability"""
    
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout = timeout_seconds
        self.settings = get_settings()
    
    def _resolve_api_key(self, api_key_ref: Optional[str]) -> Optional[str]:
        """Resolve API key from environment variable reference"""
        if not api_key_ref:
            return None
        return os.getenv(api_key_ref)
    
    async def check_model(self, model: Model) -> HealthCheckResult:
        """Perform health check on a model
        
        Args:
            model: Model to check
            
        Returns:
            HealthCheckResult with status, latency, and error if any
        """
        start_time = time.monotonic()
        
        try:
            if model.type == ModelType.LLM_CHAT:
                result = await self._check_llm(model)
            elif model.type == ModelType.EMBEDDING:
                result = await self._check_embedding(model)
            elif model.type == ModelType.RERANKER:
                result = await self._check_reranker(model)
            else:
                # For other types, just check if base_url is reachable
                result = await self._check_http_endpoint(model.base_url)
            
            latency_ms = int((time.monotonic() - start_time) * 1000)
            
            if result[0]:
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency_ms,
                    details=result[1]
                )
            else:
                return HealthCheckResult(
                    status=HealthStatus.UNAVAILABLE,
                    latency_ms=latency_ms,
                    error=result[1].get("error", "Unknown error")
                )
                
        except asyncio.TimeoutError:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            return HealthCheckResult(
                status=HealthStatus.UNAVAILABLE,
                latency_ms=latency_ms,
                error=f"Timeout after {self.timeout}s"
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(f"Health check failed for {model.alias}: {e}")
            return HealthCheckResult(
                status=HealthStatus.UNAVAILABLE,
                latency_ms=latency_ms,
                error=str(e)
            )
    
    async def _check_llm(self, model: Model) -> Tuple[bool, dict]:
        """Check LLM model by sending minimal completion request"""
        api_key = self._resolve_api_key(model.api_key_ref)
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        # Minimal request - just check if model responds
        payload = {
            "model": model.provider_model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
            "stream": False
        }
        
        url = f"{model.base_url.rstrip('/')}/chat/completions"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                return True, {
                    "model": data.get("model"),
                    "usage": data.get("usage", {})
                }
            elif response.status_code == 401:
                return False, {"error": "Authentication failed - check API key"}
            elif response.status_code == 403:
                return False, {"error": "Access forbidden - check permissions"}
            elif response.status_code == 404:
                return False, {"error": f"Model '{model.provider_model_name}' not found"}
            elif response.status_code == 429:
                # Rate limited but API is working
                return True, {"warning": "Rate limited", "status_code": 429}
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text[:200])
                except Exception:
                    error_msg = response.text[:200]
                return False, {"error": f"HTTP {response.status_code}: {error_msg}"}
    
    async def _check_embedding(self, model: Model) -> Tuple[bool, dict]:
        """Check embedding model by sending minimal embed request"""
        provider = model.provider.lower()
        
        if provider == "local":
            return await self._check_local_embedding(model)
        else:
            return await self._check_openai_embedding(model)
    
    async def _check_openai_embedding(self, model: Model) -> Tuple[bool, dict]:
        """Check OpenAI-compatible embedding API"""
        api_key = self._resolve_api_key(model.api_key_ref)
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": model.provider_model_name,
            "input": "test"
        }
        
        url = f"{model.base_url.rstrip('/')}/embeddings"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                embedding = data.get("data", [{}])[0].get("embedding", [])
                return True, {
                    "model": data.get("model"),
                    "dimensions": len(embedding),
                    "usage": data.get("usage", {})
                }
            elif response.status_code == 401:
                return False, {"error": "Authentication failed - check API key"}
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text[:200])
                except Exception:
                    error_msg = response.text[:200]
                return False, {"error": f"HTTP {response.status_code}: {error_msg}"}
    
    async def _check_local_embedding(self, model: Model) -> Tuple[bool, dict]:
        """Check local embedding service (HTTP API)"""
        # Local embedding service endpoint
        url = f"{model.base_url.rstrip('/')}/embed"
        
        # Emb service expects {"text": "string"} not {"texts": [...]}
        payload = {
            "text": "test"
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    vectors = data.get("vectors", [[]])
                    return True, {
                        "model": model.provider_model_name,
                        "dimensions": data.get("dim", len(vectors[0]) if vectors else 0)
                    }
                else:
                    return False, {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
            except httpx.ConnectError:
                return False, {"error": f"Cannot connect to {model.base_url}"}
    
    async def _check_reranker(self, model: Model) -> Tuple[bool, dict]:
        """Check reranker service"""
        url = f"{model.base_url.rstrip('/')}/rerank"
        
        payload = {
            "query": "test query",
            "documents": ["test document"],
            "top_k": 1
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                
                if response.status_code == 200:
                    return True, {"status": "ok"}
                else:
                    return False, {"error": f"HTTP {response.status_code}"}
            except httpx.ConnectError:
                return False, {"error": f"Cannot connect to {model.base_url}"}
    
    async def _check_http_endpoint(self, url: str) -> Tuple[bool, dict]:
        """Simple HTTP health check"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Try health endpoint first
                health_url = f"{url.rstrip('/')}/health"
                response = await client.get(health_url)
                if response.status_code == 200:
                    return True, {"endpoint": health_url}
                
                # Fallback to root
                response = await client.get(url)
                if response.status_code < 500:
                    return True, {"endpoint": url}
                
                return False, {"error": f"HTTP {response.status_code}"}
            except httpx.ConnectError:
                return False, {"error": f"Cannot connect to {url}"}


# Singleton instance
_health_checker: Optional[ModelHealthChecker] = None

def get_health_checker() -> ModelHealthChecker:
    """Get singleton health checker instance"""
    global _health_checker
    if _health_checker is None:
        _health_checker = ModelHealthChecker()
    return _health_checker
