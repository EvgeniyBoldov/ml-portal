"""Unit tests for health check adapters."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.model_registry import Model
from app.models.tool_instance import ToolInstance
from app.services.health.base import HealthStatus, HealthProbeResult
from app.services.health.adapters import (
    MCPHealthAdapter,
    EmbeddingHealthAdapter,
    RerankHealthAdapter,
    LLMHealthAdapter,
)


class TestMCPHealthAdapter:
    """Test cases for MCP health adapter."""
    
    @pytest.fixture
    def adapter(self):
        return MCPHealthAdapter()
    
    @pytest.fixture
    def mcp_instance(self):
        instance = MagicMock(spec=ToolInstance)
        instance.id = "test-id"
        instance.slug = "test-mcp"
        instance.url = "http://localhost:8080"
        return instance
    
    @pytest.mark.asyncio
    async def test_probe_success(self, adapter, mcp_instance):
        """Test successful MCP probe."""
        with patch('app.services.health.adapters.mcp_initialize') as mock_init:
            mock_init.return_value = {
                "protocol_version": "2024-11-05",
                "capabilities": {"tools": {}},
                "server_info": {"name": "test-server"}
            }
            
            result = await adapter.probe(mcp_instance)
            
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None
            assert result.details["protocol_version"] == "2024-11-05"
            mock_init.assert_called_once_with(
                base_url=mcp_instance.url,
                timeout=10.0
            )
    
    @pytest.mark.asyncio
    async def test_probe_no_url(self, adapter, mcp_instance):
        """Test MCP probe with no URL."""
        mcp_instance.url = None
        
        result = await adapter.probe(mcp_instance)
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "no URL configured" in result.error
    
    @pytest.mark.asyncio
    async def test_probe_invalid_response(self, adapter, mcp_instance):
        """Test MCP probe with invalid response."""
        with patch('app.services.health.adapters.mcp_initialize') as mock_init:
            mock_init.return_value = {"invalid": "response"}
            
            result = await adapter.probe(mcp_instance)
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "Invalid response" in result.error
    
    @pytest.mark.asyncio
    async def test_probe_exception(self, adapter, mcp_instance):
        """Test MCP probe with exception."""
        with patch('app.services.health.adapters.mcp_initialize') as mock_init:
            mock_init.side_effect = Exception("Connection failed")
            
            result = await adapter.probe(mcp_instance)
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "Connection failed" in result.error


class TestEmbeddingHealthAdapter:
    """Test cases for embedding health adapter."""
    
    @pytest.fixture
    def adapter(self):
        return EmbeddingHealthAdapter()
    
    @pytest.fixture
    def embedding_model(self):
        model = MagicMock(spec=Model)
        model.id = "test-id"
        model.alias = "test-embedding"
        model.endpoint = "http://localhost:8081"
        return model
    
    @pytest.mark.asyncio
    async def test_probe_success(self, adapter, embedding_model):
        """Test successful embedding probe."""
        with patch('app.services.health.adapters.EmbeddingServiceFactory.get_service') as mock_factory:
            mock_service = AsyncMock()
            mock_service.embed_text.return_value = [0.1, 0.2, 0.3, 0.4]
            mock_factory.return_value = mock_service
            
            result = await adapter.probe(embedding_model)
            
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None
            assert result.details["embedding_dim"] == 4
            assert result.details["model"] == "test-embedding"
            mock_service.embed_text.assert_called_once_with("health check")
    
    @pytest.mark.asyncio
    async def test_probe_empty_response(self, adapter, embedding_model):
        """Test embedding probe with empty response."""
        with patch('app.services.health.adapters.EmbeddingServiceFactory.get_service') as mock_factory:
            mock_service = AsyncMock()
            mock_service.embed_text.return_value = []
            mock_factory.return_value = mock_service
            
            result = await adapter.probe(embedding_model)
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "Empty embedding response" in result.error
    
    @pytest.mark.asyncio
    async def test_probe_exception(self, adapter, embedding_model):
        """Test embedding probe with exception."""
        with patch('app.services.health.adapters.EmbeddingServiceFactory.get_service') as mock_factory:
            mock_factory.side_effect = Exception("Service unavailable")
            
            result = await adapter.probe(embedding_model)
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "Service unavailable" in result.error


class TestRerankHealthAdapter:
    """Test cases for rerank health adapter."""
    
    @pytest.fixture
    def adapter(self):
        return RerankHealthAdapter()
    
    @pytest.fixture
    def rerank_model(self):
        model = MagicMock(spec=Model)
        model.id = "test-id"
        model.alias = "test-rerank"
        model.endpoint = "http://localhost:8082"
        return model
    
    @pytest.mark.asyncio
    async def test_probe_success(self, adapter, rerank_model):
        """Test successful rerank probe."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await adapter.probe(rerank_model)
            
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None
            assert result.details["model"] == "test-rerank"
            assert result.details["endpoint"] == "http://localhost:8082"
    
    @pytest.mark.asyncio
    async def test_probe_no_endpoint(self, adapter, rerank_model):
        """Test rerank probe with no endpoint."""
        rerank_model.endpoint = None
        
        result = await adapter.probe(rerank_model)
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "no endpoint configured" in result.error
    
    @pytest.mark.asyncio
    async def test_probe_http_error(self, adapter, rerank_model):
        """Test rerank probe with HTTP error."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await adapter.probe(rerank_model)
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "status 500" in result.error
    
    @pytest.mark.asyncio
    async def test_probe_connection_error(self, adapter, rerank_model):
        """Test rerank probe with connection error."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("Connection refused")
            
            result = await adapter.probe(rerank_model)
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "Connection refused" in result.error


class TestLLMHealthAdapter:
    """Test cases for LLM health adapter."""
    
    @pytest.fixture
    def adapter(self):
        return LLMHealthAdapter()
    
    @pytest.fixture
    def llm_model(self):
        model = MagicMock(spec=Model)
        model.id = "test-id"
        model.alias = "test-llm"
        model.endpoint = "http://localhost:8083"
        return model
    
    @pytest.mark.asyncio
    async def test_probe_success(self, adapter, llm_model):
        """Test successful LLM probe."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await adapter.probe(llm_model)
            
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None
            assert result.details["model"] == "test-llm"
            assert result.details["endpoint"] == "http://localhost:8083"
    
    @pytest.mark.asyncio
    async def test_probe_no_endpoint(self, adapter, llm_model):
        """Test LLM probe with no endpoint."""
        llm_model.endpoint = None
        
        result = await adapter.probe(llm_model)
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "no endpoint configured" in result.error
    
    @pytest.mark.asyncio
    async def test_probe_http_error(self, adapter, llm_model):
        """Test LLM probe with HTTP error."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 503
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await adapter.probe(llm_model)
            
            assert result.status == HealthStatus.UNHEALTHY
            assert "status 503" in result.error
