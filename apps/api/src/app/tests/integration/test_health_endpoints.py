"""
Smoke tests for health and status endpoints
"""
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.asyncio
async def test_healthz_endpoint():
    """Test /healthz endpoint returns 200 with correct format"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/healthz")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response format
        assert "status" in data
        assert data["status"] == "healthy"
        
        # Optional: check timestamp if present
        if "timestamp" in data:
            assert isinstance(data["timestamp"], str)


@pytest.mark.asyncio
async def test_readyz_endpoint():
    """Test /readyz endpoint returns 200 with correct format"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/readyz")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response format
        assert "status" in data
        assert data["status"] == "ready"
        
        # Optional: check dependencies if present
        if "dependencies" in data:
            assert isinstance(data["dependencies"], dict)


@pytest.mark.asyncio
async def test_version_endpoint():
    """Test /version endpoint returns 200 with version info"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/version")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response format
        assert "version" in data
        assert "build_time" in data
        assert "git_commit" in data
        
        # Verify version format (semantic versioning)
        version = data["version"]
        assert isinstance(version, str)
        assert len(version.split(".")) >= 2  # At least major.minor


@pytest.mark.asyncio
async def test_healthz_sync():
    """Test /healthz endpoint with sync client"""
    with TestClient(app) as client:
        response = client.get("/healthz")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_readyz_sync():
    """Test /readyz endpoint with sync client"""
    with TestClient(app) as client:
        response = client.get("/readyz")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_version_sync():
    """Test /version endpoint with sync client"""
    with TestClient(app) as client:
        response = client.get("/version")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "version" in data
        assert "build_time" in data
        assert "git_commit" in data


@pytest.mark.asyncio
async def test_health_endpoints_content_type():
    """Test that health endpoints return JSON content type"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        endpoints = ["/healthz", "/readyz", "/version"]
        
        for endpoint in endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_health_endpoints_response_time():
    """Test that health endpoints respond quickly"""
    import time
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        endpoints = ["/healthz", "/readyz", "/version"]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = await client.get(endpoint)
            end_time = time.time()
            
            assert response.status_code == 200
            # Health endpoints should respond within 1 second
            assert (end_time - start_time) < 1.0
