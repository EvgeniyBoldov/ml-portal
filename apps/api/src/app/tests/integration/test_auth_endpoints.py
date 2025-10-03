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
            # Test with valid credentials
            login_data = {
                "email": "test@example.com",
                "password": "testpassword123"
            }
            
            response = await client.post("/api/v1/auth/login", json=login_data)
            
            # Should return 404 since auth endpoints are temporarily disabled
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_auth_refresh_endpoint(self, async_client: AsyncClient):
        """Test POST /auth/refresh endpoint"""
        async for client in async_client:
            # Test with valid refresh token
            refresh_data = {
                "refresh_token": "valid_refresh_token"
            }
            
            response = await client.post("/api/v1/auth/refresh", json=refresh_data)
            
            # Should return 404 since auth endpoints are temporarily disabled
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_auth_me_endpoint(self, async_client: AsyncClient):
        """Test GET /auth/me endpoint"""
        async for client in async_client:
            # Test without authentication
            response = await client.get("/api/v1/auth/me")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_auth_logout_endpoint(self, async_client: AsyncClient):
        """Test POST /auth/logout endpoint"""
        async for client in async_client:
            # Test logout without authentication
            response = await client.post("/api/v1/auth/logout")
            assert response.status_code == 404
            
            # Test logout with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.post("/api/v1/auth/logout", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_auth_error_handling(self, async_client: AsyncClient):
        """Test auth endpoints error handling"""
        async for client in async_client:
            # Test login with missing fields
            response = await client.post("/api/v1/auth/login", json={})
            assert response.status_code == 404
            
            # Test login with invalid JSON
            response = await client.post("/api/v1/auth/login", 
                                       data="invalid json",
                                       headers={"Content-Type": "application/json"})
            assert response.status_code == 404
            
            # Test refresh with missing token
            response = await client.post("/api/v1/auth/refresh", json={})
            assert response.status_code == 404
