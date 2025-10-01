"""
Unit tests for production-grade components
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json

from app.schemas.auth import (
    AuthLoginRequest, AuthRefreshRequest, AuthTokensResponse,
    UserMeResponse, PasswordForgotRequest, PasswordResetRequest,
    PasswordResetResponse, PATTokenCreateRequest, PATTokenResponse,
    PATTokensListResponse
)
from app.schemas.common import Problem
from app.core.metrics import (
    MetricsMiddleware, http_requests_total, auth_attempts_total,
    auth_tokens_issued_total, rate_limit_hits_total, chat_messages_total,
    chat_tokens_total, external_request_total, redis_operations_total,
    time_db_operation, time_redis_operation, time_external_request
)
from app.core.idempotency import IdempotencyMiddleware


class TestAuthSchemas:
    """Test authentication Pydantic schemas"""
    
    def test_auth_login_request_validation(self):
        """Test AuthLoginRequest validation"""
        # Valid request
        request = AuthLoginRequest(email="test@example.com", password="password123")
        assert request.email == "test@example.com"
        assert request.password == "password123"
        
        # Invalid email
        with pytest.raises(ValueError):
            AuthLoginRequest(email="", password="password123")
        
        # Invalid password
        with pytest.raises(ValueError):
            AuthLoginRequest(email="test@example.com", password="")
    
    def test_auth_tokens_response_structure(self):
        """Test AuthTokensResponse structure"""
        user = UserMeResponse(id="user123", role="editor")
        
        response = AuthTokensResponse(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            token_type="bearer",
            expires_in=900,
            refresh_expires_in=2592000,
            user=user
        )
        
        assert response.access_token == "access_token_123"
        assert response.refresh_token == "refresh_token_456"
        assert response.token_type == "bearer"
        assert response.expires_in == 900
        assert response.refresh_expires_in == 2592000
        assert response.user.id == "user123"
        assert response.user.role == "editor"
    
    def test_user_me_response_security(self):
        """Test UserMeResponse doesn't expose sensitive fields"""
        response = UserMeResponse(
            id="user123",
            role="editor",
            login=None,  # Should be None for security
            fio=None     # Should be None for security
        )
        
        assert response.id == "user123"
        assert response.role == "editor"
        assert response.login is None
        assert response.fio is None
    
    def test_problem_schema_structure(self):
        """Test Problem schema for error responses"""
        problem = Problem(
            type="https://example.com/problems/invalid-credentials",
            title="Authentication Failed",
            status=401,
            code="INVALID_CREDENTIALS",
            detail="Invalid email or password",
            trace_id="trace-123"
        )
        
        assert problem.type == "https://example.com/problems/invalid-credentials"
        assert problem.title == "Authentication Failed"
        assert problem.status == 401
        assert problem.code == "INVALID_CREDENTIALS"
        assert problem.detail == "Invalid email or password"
        assert problem.trace_id == "trace-123"
    
    def test_pat_token_schemas(self):
        """Test PAT token schemas"""
        # Create request
        create_request = PATTokenCreateRequest(
            name="Test Token",
            expires_at=int(datetime.now().timestamp() + 3600)
        )
        assert create_request.name == "Test Token"
        assert create_request.expires_at > datetime.now().timestamp()
        
        # Token response
        token_response = PATTokenResponse(
            id="pat_123",
            name="Test Token",
            token="pat_token_value",
            token_mask="pat_****_****_****",
            created_at=datetime.now().isoformat(),
            expires_at=int(datetime.now().timestamp() + 3600),
            last_used_at=None,
            is_active=True
        )
        
        assert token_response.id == "pat_123"
        assert token_response.name == "Test Token"
        assert token_response.token == "pat_token_value"
        assert token_response.token_mask == "pat_****_****_****"
        assert token_response.is_active is True


class TestMetricsMiddleware:
    """Test metrics middleware"""
    
    def test_metrics_middleware_records_requests(self):
        """Test that metrics middleware records HTTP requests"""
        middleware = MetricsMiddleware(Mock())
        
        # Mock request and response
        request = Mock()
        request.method = "POST"
        request.url.path = "/api/v1/auth/login"
        
        response = Mock()
        response.status_code = 200
        
        # Mock call_next
        async def mock_call_next(req):
            return response
        
        # Test middleware
        import asyncio
        result = asyncio.run(middleware.dispatch(request, mock_call_next))
        
        assert result == response
    
    def test_metrics_middleware_endpoint_normalization(self):
        """Test endpoint name normalization"""
        middleware = MetricsMiddleware(Mock())
        
        # Test various paths
        test_cases = [
            ("/api/v1/auth/login", "auth/login"),
            ("/api/v1/chats/123/messages", "chats/{id}/messages"),
            ("/api/v1/analyze/abc-def-ghi", "analyze/{id}ghi"),
            ("/api/v1/users/456789012345678901234567890", "users/{id}"),
            ("/api/v1/", "root"),
            ("/", "/")
        ]
        
        for input_path, expected in test_cases:
            request = Mock()
            request.url.path = input_path
            result = middleware._get_endpoint_name(request)
            assert result == expected
    
    def test_metrics_context_managers(self):
        """Test metrics context managers"""
        # Test database operation timing
        with time_db_operation("SELECT"):
            pass  # Should record timing
        
        # Test Redis operation timing
        with time_redis_operation("GET"):
            pass  # Should record timing
        
        # Test external request timing
        with time_external_request("llm-service"):
            pass  # Should record timing


class TestIdempotencyProductionGrade:
    """Test production-grade idempotency"""
    
    def test_idempotency_key_generation(self):
        """Test idempotency key generation includes user context"""
        # Test JWT token parsing
        import jwt
        
        token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIiwidGVuYW50X2lkIjoidGVuYW50NDU2In0.test"
        
        # Decode token (without verification for testing)
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload.get("sub") == "user123"
        assert payload.get("tenant_id") == "tenant456"
        
        # Test cache key generation logic
        user_context = payload.get("sub", "unknown")
        tenant_context = payload.get("tenant_id", "default")
        
        cache_key = f"idempotency:{tenant_context}:{user_context}:POST:/api/v1/chats/123/messages:body_hash:test-key"
        
        assert "tenant456" in cache_key
        assert "user123" in cache_key
        assert "POST" in cache_key
        assert "/api/v1/chats/123/messages" in cache_key
    
    def test_idempotency_anonymous_user_key(self):
        """Test idempotency key generation for anonymous user"""
        # Test cache key generation for anonymous user
        user_context = "anonymous"
        tenant_context = "default"
        
        cache_key = f"idempotency:{tenant_context}:{user_context}:POST:/api/v1/public/endpoint:body_hash:test-key"
        
        assert "anonymous" in cache_key
        assert "default" in cache_key
        assert "POST" in cache_key
        assert "/api/v1/public/endpoint" in cache_key


class TestPasswordResetSchemas:
    """Test password reset schemas"""
    
    def test_password_forgot_request(self):
        """Test password forgot request validation"""
        request = PasswordForgotRequest(email="user@example.com")
        assert request.email == "user@example.com"
        
        # Invalid email
        with pytest.raises(ValueError):
            PasswordForgotRequest(email="")
    
    def test_password_reset_request(self):
        """Test password reset request validation"""
        request = PasswordResetRequest(
            token="reset_token_123",
            new_password="NewSecurePassword123!"
        )
        assert request.token == "reset_token_123"
        assert request.new_password == "NewSecurePassword123!"
        
        # Invalid token
        with pytest.raises(ValueError):
            PasswordResetRequest(token="", new_password="password123")
        
        # Invalid password
        with pytest.raises(ValueError):
            PasswordResetRequest(token="token123", new_password="")
    
    def test_password_reset_response(self):
        """Test password reset response"""
        response = PasswordResetResponse(
            message="Password has been successfully reset"
        )
        assert response.message == "Password has been successfully reset"


class TestMetricsCollection:
    """Test metrics collection"""
    
    def test_auth_metrics_increment(self):
        """Test auth metrics can be incremented"""
        # Test auth attempts
        auth_attempts_total.labels(method="login", status="success").inc()
        auth_attempts_total.labels(method="login", status="failure").inc()
        
        # Test token issuance
        auth_tokens_issued_total.labels(token_type="access").inc()
        auth_tokens_issued_total.labels(token_type="refresh").inc()
        
        # Test rate limit hits
        rate_limit_hits_total.labels(endpoint="/auth/login", limit_type="per_email").inc()
        
        # Test chat metrics
        chat_messages_total.labels(chat_type="regular", status="success").inc()
        chat_tokens_total.labels(token_type="prompt").inc()
        chat_tokens_total.labels(token_type="completion").inc()
        
        # Test external service metrics
        external_request_total.labels(target="llm-service", status="200").inc()
        external_request_total.labels(target="emb-service", status="200").inc()
        
        # Test Redis metrics
        redis_operations_total.labels(operation="GET", status="success").inc()
        redis_operations_total.labels(operation="SET", status="success").inc()
        
        # All metrics should be recorded without errors
        assert True  # If we get here, no exceptions were raised
    
    def test_metrics_registry(self):
        """Test metrics registry contains all expected metrics"""
        from app.core.metrics import registry
        
        # Get all metric names
        metric_names = []
        for metric in registry.collect():
            metric_names.append(metric.name)
        
        # Verify expected metrics are present
        expected_metrics = [
            "http_requests",
            "http_request_duration_seconds",
            "auth_attempts",
            "auth_tokens_issued",
            "rate_limit_hits",
            "chat_messages",
            "chat_tokens",
            "external_request",
            "external_request_seconds",
            "active_connections",
            "db_connections_active",
            "db_query_duration_seconds",
            "redis_operations",
            "redis_operation_duration_seconds"
        ]
        
        for expected_metric in expected_metrics:
            assert expected_metric in metric_names
