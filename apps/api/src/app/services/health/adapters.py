"""Health check adapters for different system components."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from app.models.model_registry import Model
from app.models.tool_instance import ToolInstance
from app.services.health.base import HealthCheckAdapter, HealthProbeResult, HealthStatus
from app.services.mcp_jsonrpc_client import mcp_initialize
from app.adapters.interfaces.embeddings import EmbeddingInterface, EmbeddingServiceFactory
from app.adapters.interfaces.llm import LLMClient
from app.agents.runtime.rerank_client import rerank_scores
from app.core.logging import get_logger

logger = get_logger(__name__)


class MCPHealthAdapter(HealthCheckAdapter):
    """Health check adapter for MCP connectors."""
    
    async def probe(self, target: ToolInstance) -> HealthProbeResult:
        """Probe MCP connector using initialize call."""
        if not target.url:
            return HealthProbeResult(
                status=HealthStatus.UNHEALTHY,
                error="MCP connector has no URL configured"
            )
        
        start_time = time.time()
        
        try:
            # Use MCP initialize to check connectivity
            result = await mcp_initialize(
                base_url=target.url,
                timeout=10.0  # 10 second timeout for health check
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if result.get("protocol_version"):
                return HealthProbeResult(
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency_ms,
                    details={
                        "protocol_version": result.get("protocol_version"),
                        "capabilities": result.get("capabilities", {}),
                        "server_info": result.get("server_info", {})
                    }
                )
            else:
                return HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency_ms,
                    error="Invalid response from MCP server"
                )
                
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"MCP health check failed for {target.slug}: {e}")
            return HealthProbeResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e)
            )


class EmbeddingHealthAdapter(HealthCheckAdapter):
    """Health check adapter for embedding models."""
    
    def __init__(self):
        self._test_text = "health check"
    
    async def probe(self, target: Model) -> HealthProbeResult:
        """Probe embedding model with minimal request."""
        start_time = time.time()
        
        try:
            # Use existing embedding service factory
            service: EmbeddingInterface = EmbeddingServiceFactory.get_service(target.alias)
            
            # Minimal embedding request
            result = service.embed_text(self._test_text)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if result and len(result) > 0:
                return HealthProbeResult(
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency_ms,
                    details={
                        "embedding_dim": len(result),
                        "model": target.alias
                    }
                )
            else:
                return HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency_ms,
                    error="Empty embedding response"
                )
                
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Embedding health check failed for {target.alias}: {e}")
            return HealthProbeResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e)
            )


class RerankHealthAdapter(HealthCheckAdapter):
    """Health check adapter for rerank models."""
    
    def __init__(self):
        self._test_query = "test query"
        self._test_documents = ["test document 1", "test document 2"]
    
    async def probe(self, target: Model) -> HealthProbeResult:
        """Probe rerank model with minimal request."""
        start_time = time.time()
        
        try:
            # For now, use a simple HTTP health check to the rerank endpoint
            # Full rerank functionality requires session and complex setup
            import httpx
            
            if not target.endpoint:
                return HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    error="Rerank model has no endpoint configured"
                )
            
            # Simple health check - try to reach the endpoint
            health_url = f"{target.endpoint.rstrip('/')}/health"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)
                
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                return HealthProbeResult(
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency_ms,
                    details={
                        "model": target.alias,
                        "endpoint": target.endpoint
                    }
                )
            else:
                return HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency_ms,
                    error=f"Health check failed with status {response.status_code}"
                )
                
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Rerank health check failed for {target.alias}: {e}")
            return HealthProbeResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e)
            )


class LLMHealthAdapter(HealthCheckAdapter):
    """Health check adapter for LLM models."""
    
    def __init__(self):
        self._test_messages = [{"role": "user", "content": "hi"}]
    
    async def probe(self, target: Model) -> HealthProbeResult:
        """Probe LLM model with minimal request (max_tokens=1)."""
        start_time = time.time()
        
        try:
            # For now, use a simple HTTP health check to the LLM endpoint
            # Full LLM client integration requires more complex setup
            import httpx
            
            if not target.endpoint:
                return HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    error="LLM model has no endpoint configured"
                )
            
            # Simple health check - try to reach the endpoint
            health_url = f"{target.endpoint.rstrip('/')}/health"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)
                
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                return HealthProbeResult(
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency_ms,
                    details={
                        "model": target.alias,
                        "endpoint": target.endpoint
                    }
                )
            else:
                return HealthProbeResult(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency_ms,
                    error=f"Health check failed with status {response.status_code}"
                )
                
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"LLM health check failed for {target.alias}: {e}")
            return HealthProbeResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e)
            )
