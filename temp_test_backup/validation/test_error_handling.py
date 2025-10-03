"""
Error handling and validation tests
"""
import pytest
from httpx import AsyncClient
from fastapi import status
from app.core.security import create_access_token

@pytest.mark.validation
@pytest.mark.error_handling
class TestErrorHandling:
    """Test error handling and validation"""
    
    async def test_400_bad_request(self, client: AsyncClient):
        """Test 400 Bad Request responses"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Test invalid tenant ID format
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "invalid-uuid"
            }
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        error_data = response.json()
        assert "detail" in error_data
        assert "tenant" in error_data["detail"].lower()
    
    async def test_401_unauthorized(self, client: AsyncClient):
        """Test 401 Unauthorized responses"""
        # Test without authorization header
        response = await client.get("/api/v1/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        
        error_data = response.json()
        assert "detail" in error_data
        assert "authorization" in error_data["detail"].lower()
        
        # Test with invalid token
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_403_forbidden(self, client: AsyncClient):
        """Test 403 Forbidden responses"""
        # Create user with limited permissions
        token = create_access_token(
            user_id="limited-user",
            email="limited@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]  # No write permission
        )
        
        # Try to create resource without write permission
        response = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            json={"name": "Test Chat"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        error_data = response.json()
        assert "detail" in error_data
        assert "scope" in error_data["detail"].lower() or "permission" in error_data["detail"].lower()
    
    async def test_404_not_found(self, client: AsyncClient):
        """Test 404 Not Found responses"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Try to access non-existent resource
        response = await client.get(
            "/api/v1/chats/non-existent-id",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            }
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        error_data = response.json()
        assert "detail" in error_data
    
    async def test_409_conflict(self, client: AsyncClient):
        """Test 409 Conflict responses"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Test idempotency conflict
        idempotency_key = "conflict-test-key"
        
        # First request
        response1 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "Conflict Test Chat"}
        )
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Second request with same key
        response2 = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": idempotency_key
            },
            json={"name": "Conflict Test Chat"}
        )
        
        # Should return 409 or same result
        assert response2.status_code in [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]
        
        if response2.status_code == status.HTTP_409_CONFLICT:
            error_data = response2.json()
            assert "detail" in error_data
            assert "conflict" in error_data["detail"].lower()
    
    async def test_422_unprocessable_entity(self, client: AsyncClient):
        """Test 422 Unprocessable Entity responses"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Test invalid request body
        response = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            json={"invalid_field": "value"}  # Missing required fields
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        error_data = response.json()
        assert "detail" in error_data
        
        # Should contain validation errors
        if isinstance(error_data["detail"], list):
            assert len(error_data["detail"]) > 0
            for error in error_data["detail"]:
                assert "field" in error or "loc" in error
    
    async def test_429_too_many_requests(self, client: AsyncClient):
        """Test 429 Too Many Requests responses"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Make many requests to trigger rate limiting
        responses = []
        for i in range(100):  # Large number of requests
            response = await client.post(
                "/api/v1/chat",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123"
                },
                json={"message": f"Rate limit test {i}"}
            )
            responses.append(response)
            
            # Stop if we get rate limited
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break
        
        # Check if any request was rate limited
        rate_limited = any(r.status_code == status.HTTP_429_TOO_MANY_REQUESTS for r in responses)
        
        if rate_limited:
            # Find the rate limited response
            rate_limited_response = next(r for r in responses if r.status_code == status.HTTP_429_TOO_MANY_REQUESTS)
            error_data = rate_limited_response.json()
            assert "detail" in error_data
            
            # Should contain retry information
            headers = rate_limited_response.headers
            assert "retry-after" in headers or "retry-after" in str(headers).lower()
    
    async def test_500_internal_server_error(self, client: AsyncClient):
        """Test 500 Internal Server Error responses"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Test with request that might cause server error
        response = await client.post(
            "/api/v1/chat",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            json={
                "message": "Server error test",
                "model": "error-causing-model"
            }
        )
        
        # Should handle server errors gracefully
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ]
        
        if response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR:
            error_data = response.json()
            assert "detail" in error_data
            # Should not expose internal details
            assert "traceback" not in str(error_data).lower()
            assert "exception" not in str(error_data).lower()
    
    async def test_error_response_format(self, client: AsyncClient):
        """Test error response format consistency"""
        # Test various error scenarios
        error_scenarios = [
            ("/api/v1/non-existent-endpoint", status.HTTP_404_NOT_FOUND),
            ("/api/v1/users/me", status.HTTP_401_UNAUTHORIZED),  # No auth
        ]
        
        for endpoint, expected_status in error_scenarios:
            response = await client.get(endpoint)
            assert response.status_code == expected_status
            
            error_data = response.json()
            
            # All error responses should have consistent format
            assert "detail" in error_data
            
            # Should not contain sensitive information
            error_str = str(error_data).lower()
            sensitive_terms = ["password", "secret", "key", "token", "traceback"]
            for term in sensitive_terms:
                assert term not in error_str or term in ["detail", "error"]
    
    async def test_validation_error_details(self, client: AsyncClient):
        """Test detailed validation error information"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Test with multiple validation errors
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "invalid-email",  # Invalid email format
                "password": ""  # Empty password
            }
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        error_data = response.json()
        assert "detail" in error_data
        
        # Should contain specific field errors
        if isinstance(error_data["detail"], list):
            field_errors = [error for error in error_data["detail"] if "loc" in error]
            assert len(field_errors) > 0
            
            # Should specify which fields have errors
            for error in field_errors:
                assert "loc" in error
                assert "msg" in error
                assert "type" in error
    
    async def test_error_logging(self, client: AsyncClient):
        """Test that errors are logged appropriately"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Make a request that should generate an error
        response = await client.get(
            "/api/v1/chats/invalid-id",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            }
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        
        # Check that trace headers are present (for logging correlation)
        headers = response.headers
        assert "x-trace-id" in headers or "x-span-id" in headers
