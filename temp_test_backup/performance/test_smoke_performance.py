"""
Performance smoke tests
"""
import pytest
import time
import asyncio
from httpx import AsyncClient
from fastapi import status
from app.core.security import create_access_token

@pytest.mark.performance
@pytest.mark.smoke
class TestSmokePerformance:
    """Smoke tests for performance"""
    
    async def test_auth_endpoint_performance(self, client: AsyncClient):
        """Test authentication endpoint performance"""
        start_time = time.time()
        
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123"
            }
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should respond within reasonable time
        assert duration < 2.0  # 2 seconds max
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED]
    
    async def test_user_profile_performance(self, client: AsyncClient):
        """Test user profile endpoint performance"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        start_time = time.time()
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should respond quickly
        assert duration < 1.0  # 1 second max
        assert response.status_code == status.HTTP_200_OK
    
    async def test_chat_list_performance(self, client: AsyncClient):
        """Test chat list endpoint performance"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        start_time = time.time()
        
        response = await client.get(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            params={"limit": 20}
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should respond within reasonable time
        assert duration < 2.0  # 2 seconds max
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
    
    async def test_chat_creation_performance(self, client: AsyncClient):
        """Test chat creation performance"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        start_time = time.time()
        
        response = await client.post(
            "/api/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123",
                "Idempotency-Key": "perf-test-key"
            },
            json={"name": "Performance Test Chat"}
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should respond quickly
        assert duration < 1.5  # 1.5 seconds max
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]
    
    async def test_pagination_performance(self, client: AsyncClient):
        """Test pagination performance"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Test different page sizes
        page_sizes = [10, 50, 100]
        
        for page_size in page_sizes:
            start_time = time.time()
            
            response = await client.get(
                "/api/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Id": "tenant-123"
                },
                params={"limit": page_size}
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Should respond within reasonable time regardless of page size
            assert duration < 2.0  # 2 seconds max
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
    
    async def test_concurrent_requests_performance(self, client: AsyncClient):
        """Test concurrent requests performance"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        async def make_request():
            return await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
        
        # Make 10 concurrent requests
        start_time = time.time()
        
        tasks = [make_request() for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # All requests should succeed
        for response in responses:
            assert response.status_code == status.HTTP_200_OK
        
        # Should handle concurrent requests efficiently
        assert duration < 3.0  # 3 seconds max for 10 concurrent requests
    
    async def test_health_check_performance(self, client: AsyncClient):
        """Test health check performance"""
        start_time = time.time()
        
        response = await client.get("/healthz")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Health checks should be very fast
        assert duration < 0.5  # 500ms max
        assert response.status_code == status.HTTP_200_OK
    
    async def test_readiness_check_performance(self, client: AsyncClient):
        """Test readiness check performance"""
        start_time = time.time()
        
        response = await client.get("/readyz")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Readiness checks should be reasonably fast
        assert duration < 2.0  # 2 seconds max
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]
    
    async def test_detailed_health_check_performance(self, client: AsyncClient):
        """Test detailed health check performance"""
        start_time = time.time()
        
        response = await client.get("/health")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Detailed health checks might take longer
        assert duration < 5.0  # 5 seconds max
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]
    
    async def test_jwks_endpoint_performance(self, client: AsyncClient):
        """Test JWKS endpoint performance"""
        start_time = time.time()
        
        response = await client.get("/api/v1/auth/.well-known/jwks.json")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # JWKS should be very fast
        assert duration < 0.5  # 500ms max
        assert response.status_code == status.HTTP_200_OK
    
    async def test_memory_usage_stability(self, client: AsyncClient):
        """Test memory usage stability over multiple requests"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read"]
        )
        
        # Make many requests to test memory stability
        for i in range(100):
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == status.HTTP_200_OK
            
            # Every 10 requests, check that response time is still reasonable
            if i % 10 == 0:
                start_time = time.time()
                response = await client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"}
                )
                end_time = time.time()
                duration = end_time - start_time
                
                # Response time should not degrade significantly
                assert duration < 1.0  # Still under 1 second
    
    async def test_large_payload_performance(self, client: AsyncClient):
        """Test performance with large payloads"""
        token = create_access_token(
            user_id="test-user",
            email="test@example.com",
            role="reader",
            tenant_ids=["tenant-123"],
            scopes=["read", "write"]
        )
        
        # Test with large message
        large_message = "This is a large message. " * 1000  # ~25KB message
        
        start_time = time.time()
        
        response = await client.post(
            "/api/v1/chat",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": "tenant-123"
            },
            json={
                "message": large_message,
                "model": "test-model"
            }
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle large payloads reasonably
        assert duration < 5.0  # 5 seconds max
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE]
    
    async def test_error_response_performance(self, client: AsyncClient):
        """Test error response performance"""
        # Test various error scenarios
        error_scenarios = [
            ("/api/v1/non-existent", status.HTTP_404_NOT_FOUND),
            ("/api/v1/users/me", status.HTTP_401_UNAUTHORIZED),
        ]
        
        for endpoint, expected_status in error_scenarios:
            start_time = time.time()
            
            response = await client.get(endpoint)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Error responses should be fast
            assert duration < 1.0  # 1 second max
            assert response.status_code == expected_status
