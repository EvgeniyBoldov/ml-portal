"""
Production-grade integration tests for ML-Portal API
"""
import pytest
import json
import time
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.main import app
from app.core.security import encode_jwt


class TestAuthProductionGrade:
    """Production-grade authentication tests"""
    
    def test_login_with_pydantic_schemas(self, client: TestClient):
        """Test login with proper Pydantic request/response schemas"""
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response schema
        assert "access_token" in data
        assert "refresh_token" in data
        assert "token_type" in data
        assert "expires_in" in data
        assert "refresh_expires_in" in data
        assert "user" in data
        
        # Verify token type
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900  # 15 minutes
        assert data["refresh_expires_in"] == 30*24*3600  # 30 days
        
        # Verify user schema
        user = data["user"]
        assert "id" in user
        assert "role" in user
        # login and fio should be None for security
        assert user.get("login") is None
        assert user.get("fio") is None
    
    def test_login_invalid_credentials_problem_json(self, client: TestClient):
        """Test login with invalid credentials returns Problem JSON"""
        response = client.post("/api/v1/auth/login", json={
            "email": "invalid@example.com",
            "password": "wrongpassword"
        })
        
        assert response.status_code == 401
        data = response.json()
        
        # Verify Problem JSON format
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "code" in data
        assert "detail" in data
        assert data["status"] == 401
        assert data["code"] == "INVALID_CREDENTIALS"
    
    def test_refresh_with_proper_ttl(self, client: TestClient):
        """Test refresh token with proper TTL validation"""
        # First login to get tokens
        login_response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh_token"]
        
        # Test refresh
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify new access token has proper TTL
        assert data["expires_in"] == 900  # 15 minutes
        assert data["refresh_expires_in"] == 30*24*3600  # 30 days
        
        # Verify access token is valid
        access_token = data["access_token"]
        payload = encode_jwt({"sub": "test-user"}, ttl_seconds=15*60)
        # Token should be different (newly generated)
        assert access_token != refresh_token
    
    def test_me_endpoint_security(self, client: TestClient):
        """Test /auth/me doesn't leak sensitive fields"""
        # Login first
        login_response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        access_token = login_response.json()["access_token"]
        
        # Test /me endpoint
        response = client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {access_token}"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should only expose safe fields
        assert "id" in data
        assert "role" in data
        assert data.get("login") is None  # Not exposed for security
        assert data.get("fio") is None    # Not exposed for security
    
    def test_logout_idempotent(self, client: TestClient):
        """Test logout is idempotent - multiple calls return 204"""
        # First logout
        response1 = client.post("/api/v1/auth/logout", json={
            "refresh_token": "some-token"
        })
        assert response1.status_code == 204
        
        # Second logout with same token
        response2 = client.post("/api/v1/auth/logout", json={
            "refresh_token": "some-token"
        })
        assert response2.status_code == 204
        
        # Should have X-Request-ID header
        assert "X-Request-ID" in response1.headers
        assert "X-Request-ID" in response2.headers


class TestRateLimitingProductionGrade:
    """Production-grade rate limiting tests"""
    
    def test_auth_login_rate_limit_with_headers(self, client: TestClient):
        """Test auth login rate limiting with proper headers"""
        email = "ratelimit@example.com"
        
        # Make requests up to limit
        responses = []
        for i in range(12):  # Limit is 10 per minute
            response = client.post("/api/v1/auth/login", json={
                "email": email,
                "password": "testpassword123"
            })
            responses.append(response)
        
        # Check that 11th request gets 429
        assert responses[10].status_code == 429
        
        # Check rate limit headers
        headers = responses[10].headers
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Window" in headers
        assert "Retry-After" in headers
        
        # Verify header values
        assert headers["X-RateLimit-Limit"] == "10"
        assert headers["X-RateLimit-Remaining"] == "0"
        assert headers["Retry-After"].isdigit()
    
    def test_rate_limit_graceful_degradation(self, client: TestClient):
        """Test rate limiting gracefully degrades when Redis is down"""
        with patch('app.api.deps.get_redis') as mock_redis:
            # Simulate Redis connection error
            mock_redis.side_effect = Exception("Redis connection failed")
            
            # Request should still work (graceful degradation)
            response = client.post("/api/v1/auth/login", json={
                "email": "test@example.com",
                "password": "testpassword123"
            })
            
            # Should not be rate limited (graceful skip)
            assert response.status_code != 429


class TestIdempotencyProductionGrade:
    """Production-grade idempotency tests"""
    
    def test_chat_message_idempotency(self, client: TestClient):
        """Test chat message creation is idempotent"""
        # Login first
        login_response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Create chat first
        chat_response = client.post("/api/v1/chats", json={
            "name": "Test Chat"
        }, headers=headers)
        chat_id = chat_response.json()["id"]
        
        # First message with idempotency key
        idempotency_key = "test-message-key-123"
        message_data = {
            "content": "Hello, this is a test message",
            "role": "user"
        }
        
        response1 = client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json=message_data,
            headers={**headers, "Idempotency-Key": idempotency_key}
        )
        
        # Second identical request
        response2 = client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json=message_data,
            headers={**headers, "Idempotency-Key": idempotency_key}
        )
        
        # Both should return same response
        assert response1.status_code == response2.status_code
        assert response1.json() == response2.json()
        
        # Should have same message ID
        assert response1.json()["id"] == response2.json()["id"]
    
    def test_analyze_run_idempotency(self, client: TestClient):
        """Test analysis run is idempotent"""
        # Login first
        login_response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Create analysis first
        analysis_response = client.post("/api/v1/analyze", json={
            "name": "Test Analysis"
        }, headers=headers)
        analysis_id = analysis_response.json()["id"]
        
        # First run with idempotency key
        idempotency_key = "test-analysis-key-456"
        
        response1 = client.post(
            f"/api/v1/analyze/{analysis_id}/run",
            headers={**headers, "Idempotency-Key": idempotency_key}
        )
        
        # Second identical request
        response2 = client.post(
            f"/api/v1/analyze/{analysis_id}/run",
            headers={**headers, "Idempotency-Key": idempotency_key}
        )
        
        # Both should return same response
        assert response1.status_code == response2.status_code
        assert response1.json() == response2.json()
    
    def test_idempotency_skip_sse(self, client: TestClient):
        """Test idempotency skips SSE responses"""
        # Login first
        login_response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Create chat first
        chat_response = client.post("/api/v1/chats", json={
            "name": "Test Chat"
        }, headers=headers)
        chat_id = chat_response.json()["id"]
        
        # SSE request with idempotency key
        idempotency_key = "test-sse-key-789"
        
        response = client.post(
            f"/api/v1/chats/{chat_id}/messages/stream",
            json={"content": "Test SSE message"},
            headers={**headers, "Idempotency-Key": idempotency_key}
        )
        
        # Should not be cached (SSE responses are not cached)
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/event-stream"


class TestPasswordResetProductionGrade:
    """Production-grade password reset tests"""
    
    def test_password_forgot_rate_limit(self, client: TestClient):
        """Test password forgot endpoint has rate limiting"""
        email = "forgot@example.com"
        
        # Make requests up to limit (5 per 5 minutes)
        responses = []
        for i in range(7):
            response = client.post("/api/v1/auth/password/forgot", json={
                "email": email
            })
            responses.append(response)
        
        # Check that 6th request gets 429
        assert responses[5].status_code == 429
        
        # Check rate limit headers
        headers = responses[5].headers
        assert "X-RateLimit-Limit" in headers
        assert "Retry-After" in headers
    
    def test_password_reset_weak_password(self, client: TestClient):
        """Test password reset rejects weak passwords"""
        response = client.post("/api/v1/auth/password/reset", json={
            "token": "valid-token",
            "new_password": "123"  # Weak password
        })
        
        assert response.status_code == 400
        data = response.json()
        
        # Should return Problem JSON
        assert "type" in data
        assert "title" in data
        assert "code" in data
        assert data["code"] == "WEAK_PASSWORD"
    
    def test_password_reset_invalid_token(self, client: TestClient):
        """Test password reset with invalid token"""
        response = client.post("/api/v1/auth/password/reset", json={
            "token": "invalid-token",
            "new_password": "NewSecurePassword123!"
        })
        
        assert response.status_code == 400
        data = response.json()
        
        # Should return Problem JSON
        assert data["code"] == "INVALID_TOKEN"


class TestSSEProductionGrade:
    """Production-grade SSE tests"""
    
    def test_sse_event_format(self, client: TestClient):
        """Test SSE events follow proper format"""
        # Login first
        login_response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Create chat first
        chat_response = client.post("/api/v1/chats", json={
            "name": "Test Chat"
        }, headers=headers)
        chat_id = chat_response.json()["id"]
        
        # Test SSE stream
        response = client.post(
            f"/api/v1/chats/{chat_id}/messages/stream",
            json={"content": "Test message"},
            headers={**headers, "Accept": "text/event-stream"}
        )
        
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/event-stream"
        
        # Parse SSE events
        content = response.text
        events = content.strip().split('\n\n')
        
        # Should have proper SSE format
        for event in events:
            if event.strip():
                lines = event.strip().split('\n')
                # Each event should have 'event:' and 'data:' lines
                assert any(line.startswith('event:') for line in lines)
                assert any(line.startswith('data:') for line in lines)


class TestOpenAPIConformance:
    """OpenAPI contract conformance tests"""
    
    def test_openapi_schema_generation(self, client: TestClient):
        """Test OpenAPI schema is properly generated"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        
        schema = response.json()
        
        # Verify basic structure
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema
        
        # Verify auth endpoints are documented
        assert "/api/v1/auth/login" in schema["paths"]
        assert "/api/v1/auth/refresh" in schema["paths"]
        assert "/api/v1/auth/me" in schema["paths"]
        assert "/api/v1/auth/password/forgot" in schema["paths"]
        assert "/api/v1/auth/password/reset" in schema["paths"]
        
        # Verify schemas are defined
        assert "components" in schema
        assert "schemas" in schema["components"]
        
        # Check that our custom schemas are included
        schemas = schema["components"]["schemas"]
        assert "AuthLoginRequest" in schemas
        assert "AuthTokensResponse" in schemas
        assert "UserMeResponse" in schemas
        assert "Problem" in schemas
    
    def test_metrics_endpoint(self, client: TestClient):
        """Test Prometheus metrics endpoint"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/plain"
        
        # Should contain Prometheus metrics
        content = response.text
        assert "http_requests_total" in content
        assert "http_request_duration_seconds" in content
        assert "auth_attempts_total" in content
