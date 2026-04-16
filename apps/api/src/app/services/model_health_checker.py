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

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_registry import Model, ModelType, HealthStatus
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.credential_service import CredentialService, CredentialError

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
    
    async def _resolve_api_key(self, model: Model, session: Optional[AsyncSession] = None) -> Optional[str]:
        """Resolve API key via CredentialService, fallback to instance.config"""
        # 1. Try CredentialService (new approach)
        if session and model.instance_id:
            try:
                cred_service = CredentialService(session)
                decrypted = await cred_service.resolve_credentials(
                    instance_id=model.instance_id,
                    strategy="ANY",
                )
                if decrypted:
                    payload = decrypted.payload
                    # Support different auth types
                    if decrypted.auth_type == "api_key":
                        return payload.get("api_key")
                    elif decrypted.auth_type == "token":
                        return payload.get("token")
                    elif decrypted.auth_type == "basic":
                        return payload.get("password")
            except CredentialError as e:
                logger.warning(f"Failed to resolve credentials for model {model.alias}: {e}")
        
        # 2. Fallback: instance.config (legacy)
        if model.instance and model.instance.config:
            api_key = model.instance.config.get("api_key")
            if api_key:
                return api_key
            api_key_ref = model.instance.config.get("api_key_ref")
            if api_key_ref:
                return os.getenv(api_key_ref)
        return None
    
    def _resolve_base_url(self, model: Model) -> Optional[str]:
        """Resolve base URL from instance or extra_config"""
        if model.base_url:
            return model.base_url
        # Try instance url first
        if model.instance and model.instance.url:
            return model.instance.url
        # Fallback to extra_config
        if model.extra_config and model.extra_config.get("base_url"):
            return model.extra_config["base_url"]
        return None
    
    async def check_model(self, model: Model, session: Optional[AsyncSession] = None) -> HealthCheckResult:
        """Perform health check on a model
        
        Args:
            model: Model to check
            
        Returns:
            HealthCheckResult with status, latency, and error if any
        """
        start_time = time.monotonic()
        
        try:
            if model.type == ModelType.LLM_CHAT:
                result = await self._check_llm(model, session)
            elif model.type == ModelType.EMBEDDING:
                result = await self._check_embedding(model, session)
            elif model.type == ModelType.RERANKER:
                result = await self._check_reranker(model)
            else:
                # For other types, just check if base_url is reachable
                base_url = self._resolve_base_url(model)
                if not base_url:
                    return HealthCheckResult(
                        status=HealthStatus.UNAVAILABLE,
                        latency_ms=0,
                        error="No base URL configured (no instance linked)"
                    )
                result = await self._check_http_endpoint(base_url)
            
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
    
    async def _check_llm(self, model: Model, session: Optional[AsyncSession] = None) -> Tuple[bool, dict]:
        """Check LLM model by sending minimal completion request"""
        base_url = self._resolve_base_url(model)
        if not base_url:
            return False, {"error": "No base URL configured (no instance linked)"}
        
        api_key = await self._resolve_api_key(model, session)
        
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
        
        url = f"{base_url.rstrip('/')}/chat/completions"
        
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
    
    async def _check_embedding(self, model: Model, session: Optional[AsyncSession] = None) -> Tuple[bool, dict]:
        """Check embedding model by sending minimal embed request"""
        connector = (model.connector or "").lower()
        
        if connector == "local_emb_http":
            return await self._check_local_embedding(model)
        else:
            return await self._check_openai_embedding(model, session)
    
    async def _check_openai_embedding(self, model: Model, session: Optional[AsyncSession] = None) -> Tuple[bool, dict]:
        """Check OpenAI-compatible embedding API"""
        base_url = self._resolve_base_url(model)
        if not base_url:
            return False, {"error": "No base URL configured (no instance linked)"}
        
        api_key = await self._resolve_api_key(model, session)
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": model.provider_model_name,
            "input": "test"
        }
        
        url = f"{base_url.rstrip('/')}/embeddings"
        
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
        base_url = self._resolve_base_url(model)
        if not base_url:
            return False, {"error": "No base URL configured (no instance linked)"}
        
        # Local embedding service endpoint
        url = f"{base_url.rstrip('/')}/embed"
        
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
                return False, {"error": f"Cannot connect to {base_url}"}
    
    async def _check_reranker(self, model: Model) -> Tuple[bool, dict]:
        """Check reranker service"""
        base_url = self._resolve_base_url(model)
        if not base_url:
            return False, {"error": "No base URL configured (no instance linked)"}

        candidate_base_urls = [base_url]
        if "://reranker:" in base_url:
            candidate_base_urls.append(base_url.replace("://reranker:", "://rerank:"))
        if self.settings.RERANK_SERVICE_URL:
            candidate_base_urls.append(self.settings.RERANK_SERVICE_URL)
        deduped_candidates: list[str] = []
        for item in candidate_base_urls:
            if item and item not in deduped_candidates:
                deduped_candidates.append(item)

        payload = {
            "query": "test query",
            "documents": ["test document"],
            "top_k": 1
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            errors: list[str] = []
            for candidate in deduped_candidates:
                url = f"{candidate.rstrip('/')}/rerank"
                try:
                    response = await client.post(url, json=payload)
                except httpx.ConnectError:
                    errors.append(f"{url}: connect error")
                    continue

                if response.status_code == 200:
                    return True, {"status": "ok", "endpoint": candidate}
                errors.append(f"{url}: HTTP {response.status_code}")
            return False, {"error": " ; ".join(errors) or f"Cannot connect to {base_url}"}
    
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
