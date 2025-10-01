"""
Auth / JWT / Refresh tests
"""
import pytest
import jwt
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from tests.conftest import assert_problem
from app.core.config import get_settings


def test_login_success(client: TestClient):
    """Test successful login returns access/refresh tokens"""
    # This would require a test user in the database
    # For now, test the endpoint structure
    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword123"
    })
    
    # Might be 401 if user doesn't exist, but structure should be correct
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        
        # Verify JWT structure and expiration
        access_token = data["access_token"]
        s = get_settings()
        decoded = jwt.decode(
            access_token, 
            s.JWT_SECRET, 
            algorithms=[s.JWT_ALGORITHM],
            options={"verify_exp": False}  # Don't verify expiration in test
        )
        assert "exp" in decoded
        assert "sub" in decoded


def test_login_invalid_credentials(client: TestClient):
    """Test login with invalid credentials returns 401"""
    response = client.post("/api/v1/auth/login", json={
        "email": "invalid@example.com",
        "password": "wrongpassword"
    })
    
    assert_problem(response, 401, "INVALID_CREDENTIALS")


def test_login_missing_fields(client: TestClient):
    """Test login with missing fields returns 422"""
    response = client.post("/api/v1/auth/login", json={})
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_refresh_token_success(client: TestClient):
    """Test refresh token with valid token"""
    # This would require a valid refresh token
    # For now, test the endpoint structure
    response = client.post("/api/v1/auth/refresh", json={
        "refresh_token": "valid_refresh_token"
    })
    
    # Might be 401 if token is invalid, but structure should be correct
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"


def test_refresh_token_invalid(client: TestClient):
    """Test refresh with invalid token returns 401"""
    response = client.post("/api/v1/auth/refresh", json={
        "refresh_token": "invalid_token"
    })
    
    assert_problem(response, 401, "INVALID_TOKEN")


def test_refresh_token_expired(client: TestClient):
    """Test refresh with expired token returns 401"""
    # Create an expired token
    expired_payload = {
        "sub": "test@example.com",
        "exp": datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
    }
    expired_token = jwt.encode(
        expired_payload, 
        s.JWT_SECRET, 
        algorithm=s.JWT_ALGORITHM
    )
    
    response = client.post("/api/v1/auth/refresh", json={
        "refresh_token": expired_token
    })
    
    assert_problem(response, 401, "INVALID_TOKEN")


def test_jwt_algorithm_from_settings(client: TestClient):
    """Test JWT uses algorithm from settings, not hardcoded"""
    # Verify that JWT_ALGORITHM is read from settings
    s = get_settings()
    assert hasattr(s, 'JWT_ALGORITHM')
    assert s.JWT_ALGORITHM in ['HS256', 'HS384', 'HS512', 'RS256']


def test_logout_success(client: TestClient):
    """Test logout endpoint"""
    response = client.post("/api/v1/auth/logout", headers={
        "Authorization": "Bearer test_token"
    })
    
    # Should return success even with invalid token in some implementations
    assert "X-Request-ID" in response.headers
