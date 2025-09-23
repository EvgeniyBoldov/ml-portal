"""
Unit tests for middleware components
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from fastapi import Request, Response
from fastapi.testclient import TestClient
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.core.request_id import RequestIDMiddleware
from app.core.security_headers import SecurityHeadersMiddleware


class TestRequestIDMiddleware:
    """Test RequestIDMiddleware"""
    
    @pytest.mark.asyncio
    async def test_request_id_middleware(self):
        """Test request ID middleware adds request ID"""
        app = Mock()
        middleware = RequestIDMiddleware(app)
        
        request = Mock()
        request.headers = {}
        call_next = AsyncMock(return_value=Response())
        
        response = await middleware.dispatch(request, call_next)
        
        assert call_next.called
        # Request ID should be added to response headers
        assert 'X-Request-ID' in response.headers
    
    @pytest.mark.asyncio
    async def test_request_id_from_header(self):
        """Test request ID from existing header"""
        app = Mock()
        middleware = RequestIDMiddleware(app)
        
        request = Mock()
        request.headers = {"X-Request-ID": "existing-id"}
        call_next = AsyncMock(return_value=Response())
        
        response = await middleware.dispatch(request, call_next)
        
        assert call_next.called
        # Should use existing request ID
        assert response.headers['X-Request-ID'] == "existing-id"


class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware"""
    
    @pytest.mark.asyncio
    async def test_security_headers_middleware(self):
        """Test security headers middleware adds headers"""
        app = Mock()
        middleware = SecurityHeadersMiddleware(app)
        
        request = Mock()
        request.url.scheme = "http"  # Set scheme for test
        response = Response()
        call_next = AsyncMock(return_value=response)
        
        result = await middleware.dispatch(request, call_next)
        
        assert call_next.called
        # Security headers should be added to response
        assert 'X-Frame-Options' in result.headers
    
    @pytest.mark.asyncio
    async def test_security_headers_content(self):
        """Test specific security headers content"""
        app = Mock()
        middleware = SecurityHeadersMiddleware(app)
        
        request = Mock()
        request.url.scheme = "http"  # Set scheme for test
        response = Response()
        call_next = AsyncMock(return_value=response)
        
        result = await middleware.dispatch(request, call_next)
        
        # Check that security headers are present
        assert result.headers['X-Frame-Options'] == 'DENY'
        assert result.headers['X-Content-Type-Options'] == 'nosniff'
        assert "X-Content-Type-Options" in response.headers
        assert "X-Frame-Options" in response.headers
        assert "X-XSS-Protection" in response.headers