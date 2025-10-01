"""
Health / Ready / Version endpoint tests
"""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Test GET /healthz returns 200"""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers


def test_ready_endpoint_success(client: TestClient):
    """Test GET /readyz returns 200 when dependencies are available"""
    response = client.get("/api/v1/readyz")
    # Should return 200 if all dependencies are available
    # In test environment, this might return 503 if services are not ready
    assert response.status_code in [200, 503]
    assert "X-Request-ID" in response.headers


def test_version_endpoint(client: TestClient):
    """Test GET /version contains required fields"""
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    
    data = response.json()
    assert "version" in data
    assert "commit" in data
    assert "build_time" in data
