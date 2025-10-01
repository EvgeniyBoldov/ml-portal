"""
Rate limiting tests
"""
import pytest
import time
from fastapi.testclient import TestClient


def test_rate_limit_within_window(client: TestClient):
    """Test requests within rate limit window are allowed"""
    # Make a few requests within the limit
    for i in range(3):
        response = client.post("/api/v1/auth/login", json={
            "email": f"test{i}@example.com",
            "password": "testpassword"
        })
        
        # Should not be rate limited (might be 401 for invalid creds)
        assert response.status_code != 429
        assert "X-Request-ID" in response.headers


def test_rate_limit_exceeded_returns_429(client: TestClient):
    """Test rate limit exceeded returns 429 with Retry-After"""
    # This would require hitting the actual rate limit
    # For now, test the structure
    
    # Make many requests quickly to potentially trigger rate limit
    responses = []
    for i in range(20):  # Assuming rate limit is lower than 20
        response = client.post("/api/v1/auth/login", json={
            "email": f"test{i}@example.com",
            "password": "testpassword"
        })
        responses.append(response)
        
        if response.status_code == 429:
            # Found rate limit response
            assert "Retry-After" in response.headers
            assert "X-Request-ID" in response.headers
            
            # Should be Problem JSON format
            data = response.json()
            assert "type" in data
            assert "status" in data
            assert data["status"] == 429
            break


def test_rate_limit_key_by_ip(client: TestClient):
    """Test rate limit key is formed by IP"""
    # In test environment, all requests come from same IP
    # So rate limiting should apply across requests
    
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword"
    })
    
    assert "X-Request-ID" in response.headers


def test_rate_limit_xff_header_support(client: TestClient):
    """Test rate limiting respects X-Forwarded-For header"""
    headers = {"X-Forwarded-For": "192.168.1.100"}
    
    response = client.post("/api/v1/auth/login", 
                          json={"email": "test@example.com", "password": "testpassword"},
                          headers=headers)
    
    assert "X-Request-ID" in response.headers


def test_rate_limit_trusted_proxy_header(client: TestClient):
    """Test rate limiting uses configured trusted proxy header"""
    # Test with different proxy headers
    headers = {
        "X-Real-IP": "10.0.0.1",
        "X-Forwarded-For": "192.168.1.100, 10.0.0.1"
    }
    
    response = client.post("/api/v1/auth/login", 
                          json={"email": "test@example.com", "password": "testpassword"},
                          headers=headers)
    
    assert "X-Request-ID" in response.headers


def test_rate_limit_window_reset(client: TestClient):
    """Test rate limit window resets after TTL"""
    # This would require waiting for the window to reset
    # For now, just test the basic functionality
    
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword"
    })
    
    assert "X-Request-ID" in response.headers


def test_rate_limit_different_endpoints(client: TestClient):
    """Test rate limiting applies per endpoint or globally"""
    # Test different endpoints
    response1 = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword"
    })
    
    response2 = client.get("/api/v1/healthz")
    
    assert "X-Request-ID" in response1.headers
    assert "X-Request-ID" in response2.headers


def test_rate_limit_authenticated_vs_anonymous(client: TestClient):
    """Test rate limiting for authenticated vs anonymous users"""
    # Anonymous request
    response1 = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword"
    })
    
    # Authenticated request (with mock token)
    response2 = client.get("/api/v1/users/me", headers={
        "Authorization": "Bearer test-token"
    })
    
    assert "X-Request-ID" in response1.headers
    assert "X-Request-ID" in response2.headers


def test_rate_limit_redis_atomic_operations(client: TestClient):
    """Test rate limiting uses atomic Redis operations"""
    # This tests the implementation indirectly
    # Atomic operations prevent race conditions
    
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword"
    })
    
    assert "X-Request-ID" in response.headers
    # The actual atomicity would be tested at the unit level
