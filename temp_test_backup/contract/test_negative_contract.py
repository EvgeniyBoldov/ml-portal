"""
Negative contract tests - testing invalid inputs and edge cases
"""
import pytest
from httpx import AsyncClient
from fastapi import status

@pytest.mark.contract
@pytest.mark.negative
class TestNegativeContract:
    """Test negative scenarios and edge cases"""
    
    async def test_invalid_json_payload(self, client: AsyncClient):
        """Test invalid JSON payload"""
        response = await client.post(
            "/api/v1/auth/login",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_missing_required_fields(self, client: AsyncClient):
        """Test missing required fields"""
        response = await client.post(
            "/api/v1/auth/login",
            json={}  # Missing email and password
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_invalid_field_types(self, client: AsyncClient):
        """Test invalid field types"""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": 123,  # Should be string
                "password": True  # Should be string
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_unknown_fields(self, client: AsyncClient):
        """Test unknown fields in request"""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",
                "unknown_field": "should_be_ignored"
            }
        )
        # Should still process the request (unknown fields ignored)
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_ENTITY]
    
    async def test_invalid_email_format(self, client: AsyncClient):
        """Test invalid email format"""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "not-an-email",
                "password": "password123"
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_empty_strings(self, client: AsyncClient):
        """Test empty string values"""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "",
                "password": ""
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_null_values(self, client: AsyncClient):
        """Test null values"""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": None,
                "password": None
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_very_long_strings(self, client: AsyncClient):
        """Test very long string values"""
        long_string = "a" * 10000
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": long_string,
                "password": long_string
            }
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_special_characters(self, client: AsyncClient):
        """Test special characters in input"""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "password with spaces and special chars !@#$%^&*()"
            }
        )
        # Should handle special characters gracefully
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_ENTITY]
    
    async def test_unicode_characters(self, client: AsyncClient):
        """Test unicode characters"""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "тест@example.com",
                "password": "пароль123"
            }
        )
        # Should handle unicode gracefully
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_ENTITY]

@pytest.mark.contract
@pytest.mark.headers
class TestHeaderValidation:
    """Test header validation"""
    
    async def test_missing_tenant_header(self, client: AsyncClient):
        """Test missing X-Tenant-Id header"""
        response = await client.get("/api/v1/chats")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_invalid_tenant_header_format(self, client: AsyncClient):
        """Test invalid X-Tenant-Id header format"""
        response = await client.get(
            "/api/v1/chats",
            headers={"X-Tenant-Id": "not-a-uuid"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_empty_tenant_header(self, client: AsyncClient):
        """Test empty X-Tenant-Id header"""
        response = await client.get(
            "/api/v1/chats",
            headers={"X-Tenant-Id": ""}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_invalid_idempotency_key_format(self, client: AsyncClient):
        """Test invalid Idempotency-Key format"""
        response = await client.post(
            "/api/v1/chats",
            headers={"Idempotency-Key": "invalid key with spaces"},
            json={"name": "test chat"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_too_long_idempotency_key(self, client: AsyncClient):
        """Test too long Idempotency-Key"""
        long_key = "a" * 300  # Exceeds max length
        response = await client.post(
            "/api/v1/chats",
            headers={"Idempotency-Key": long_key},
            json={"name": "test chat"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_missing_authorization_header(self, client: AsyncClient):
        """Test missing Authorization header"""
        response = await client.get("/api/v1/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_invalid_authorization_format(self, client: AsyncClient):
        """Test invalid Authorization header format"""
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "InvalidFormat token123"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_malformed_bearer_token(self, client: AsyncClient):
        """Test malformed Bearer token"""
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.contract
@pytest.mark.query_params
class TestQueryParameterValidation:
    """Test query parameter validation"""
    
    async def test_invalid_limit_parameter(self, client: AsyncClient):
        """Test invalid limit parameter"""
        response = await client.get(
            "/api/v1/chats",
            params={"limit": "not-a-number"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_limit_out_of_range(self, client: AsyncClient):
        """Test limit out of allowed range"""
        # Test limit too small
        response = await client.get(
            "/api/v1/chats",
            params={"limit": 0}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test limit too large
        response = await client.get(
            "/api/v1/chats",
            params={"limit": 1000}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_invalid_cursor_format(self, client: AsyncClient):
        """Test invalid cursor format"""
        response = await client.get(
            "/api/v1/chats",
            params={"cursor": "invalid-cursor-format"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    async def test_invalid_order_parameter(self, client: AsyncClient):
        """Test invalid order parameter"""
        response = await client.get(
            "/api/v1/chats",
            params={"order": "invalid-order"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_multiple_values_for_single_param(self, client: AsyncClient):
        """Test multiple values for single parameter"""
        response = await client.get(
            "/api/v1/chats",
            params=[("limit", "10"), ("limit", "20")]  # Multiple limit values
        )
        # Should handle gracefully (use first or last value)
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
