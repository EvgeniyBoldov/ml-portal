"""
Integration tests for Auth API endpoints
"""
import pytest
import uuid
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
class TestAuthEndpoints:
    """Integration tests for Auth API endpoints."""

    @pytest.mark.asyncio
    async def test_auth_login_endpoint(self, async_client: AsyncClient):
        """Test POST /auth/login endpoint"""
        async for client in async_client:
            # Test with invalid credentials (should return 401)
            login_data = {
                "email": "nonexistent@example.com",
                "password": "wrongpassword"
            }
            
            response = await client.post("/api/v1/auth/login", json=login_data)
            assert response.status_code == 401
            
            # Test with missing fields (should return 422)
            response = await client.post("/api/v1/auth/login", json={})
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_auth_refresh_endpoint(self, async_client: AsyncClient):
        """Test POST /auth/refresh endpoint"""
        async for client in async_client:
            # Test with invalid refresh token (should return 401)
            refresh_data = {
                "refresh_token": "invalid_refresh_token"
            }
            
            response = await client.post("/api/v1/auth/refresh", json=refresh_data)
            assert response.status_code == 401
            
            # Test with missing token (should return 422)
            response = await client.post("/api/v1/auth/refresh", json={})
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_auth_me_endpoint(self, async_client: AsyncClient):
        """Test GET /auth/me endpoint"""
        async for client in async_client:
            # Test without authentication (should return 401)
            response = await client.get("/api/v1/auth/me")
            assert response.status_code == 401
            
            # Test with invalid token (should return 401)
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_auth_logout_endpoint(self, async_client: AsyncClient):
        """Test POST /auth/logout endpoint"""
        async for client in async_client:
            # Test logout without authentication (should return 204)
            response = await client.post("/api/v1/auth/logout")
            assert response.status_code == 204
            
            # Test logout with invalid token (should return 204)
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.post("/api/v1/auth/logout", headers=headers)
            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_auth_error_handling(self, async_client: AsyncClient):
        """Test auth endpoints error handling"""
        async for client in async_client:
            # Test login with missing fields (should return 422)
            response = await client.post("/api/v1/auth/login", json={})
            assert response.status_code == 422
            
            # Test login with invalid JSON (should return 422)
            response = await client.post("/api/v1/auth/login", 
                                       data="invalid json",
                                       headers={"Content-Type": "application/json"})
            assert response.status_code == 422
            
            # Test refresh with missing token (should return 422)
            response = await client.post("/api/v1/auth/refresh", json={})
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_jwks_endpoint(self, async_client: AsyncClient):
        """Test GET /.well-known/jwks.json endpoint"""
        async for client in async_client:
            response = await client.get("/api/v1/auth/.well-known/jwks.json")
            assert response.status_code == 200
            
            data = response.json()
            assert "keys" in data
            assert len(data["keys"]) > 0
