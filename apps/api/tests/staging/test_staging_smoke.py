"""
Staging environment smoke tests
"""
import pytest
import httpx
import os
from typing import Dict, Any


class TestStagingSmoke:
    """Smoke tests for staging environment"""
    
    @pytest.fixture
    def api_base_url(self) -> str:
        """Get API base URL from environment"""
        return os.getenv("API_BASE_URL", "http://localhost:8000")
    
    @pytest.fixture
    def client(self, api_base_url: str) -> httpx.AsyncClient:
        """Create HTTP client for API calls"""
        return httpx.AsyncClient(base_url=api_base_url, timeout=30.0)
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: httpx.AsyncClient):
        """Test that health endpoint is accessible"""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_database_connectivity(self, client: httpx.AsyncClient):
        """Test database connectivity through health endpoint"""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "services" in data
        
        # Check database status
        services = data["services"]
        assert "database" in services
        assert services["database"]["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_redis_connectivity(self, client: httpx.AsyncClient):
        """Test Redis connectivity through health endpoint"""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        services = data["services"]
        
        # Check Redis status if available
        if "redis" in services:
            assert services["redis"]["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_auth_endpoints_accessible(self, client: httpx.AsyncClient):
        """Test that auth endpoints are accessible"""
        # Test login endpoint (should return 422 for missing data, not 404)
        response = await client.post("/api/v1/auth/login")
        assert response.status_code == 422  # Validation error, not 404
    
    @pytest.mark.asyncio
    async def test_api_documentation_accessible(self, client: httpx.AsyncClient):
        """Test that API documentation is accessible"""
        response = await client.get("/docs")
        assert response.status_code == 200
        
        # Check that it's HTML
        assert "text/html" in response.headers.get("content-type", "")
    
    @pytest.mark.asyncio
    async def test_openapi_schema_accessible(self, client: httpx.AsyncClient):
        """Test that OpenAPI schema is accessible"""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data
    
    @pytest.mark.asyncio
    async def test_cors_headers(self, client: httpx.AsyncClient):
        """Test CORS headers are present"""
        response = await client.options("/api/v1/health")
        
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
    
    @pytest.mark.asyncio
    async def test_response_times(self, client: httpx.AsyncClient):
        """Test that response times are acceptable"""
        import time
        
        start_time = time.time()
        response = await client.get("/api/v1/health")
        end_time = time.time()
        
        response_time = end_time - start_time
        
        assert response.status_code == 200
        assert response_time < 5.0  # Should respond within 5 seconds
    
    @pytest.mark.asyncio
    async def test_error_handling(self, client: httpx.AsyncClient):
        """Test error handling for non-existent endpoints"""
        response = await client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_environment_variables(self, client: httpx.AsyncClient):
        """Test that environment is properly configured"""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check that environment info is present
        assert "environment" in data or "env" in data
