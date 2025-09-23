"""
Unit tests for error handlers
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.core.error_handling import (
    create_error_response,
    raise_bad_request,
    raise_unauthorized,
    raise_forbidden,
    raise_not_found,
    raise_conflict,
    raise_validation_error,
    raise_server_error,
    install_exception_handlers
)


class TestErrorHandling:
    """Test error handling functions"""
    
    def test_create_error_response(self):
        """Test creating error response"""
        response = create_error_response(
            message="Test error",
            code="test_error",
            details={"field": "value"}
        )
        
        assert response.error.message == "Test error"
        assert response.error.code == "test_error"
        assert response.error.details == {"field": "value"}
        assert response.timestamp is not None
    
    def test_raise_bad_request(self):
        """Test raising bad request error"""
        with pytest.raises(HTTPException) as exc_info:
            raise_bad_request("Bad request", {"field": "value"})
        
        assert exc_info.value.status_code == 400
        assert "Bad request" in str(exc_info.value.detail)
    
    def test_raise_unauthorized(self):
        """Test raising unauthorized error"""
        with pytest.raises(HTTPException) as exc_info:
            raise_unauthorized("Unauthorized")
        
        assert exc_info.value.status_code == 401
        assert "Unauthorized" in str(exc_info.value.detail)
    
    def test_raise_forbidden(self):
        """Test raising forbidden error"""
        with pytest.raises(HTTPException) as exc_info:
            raise_forbidden("Forbidden")
        
        assert exc_info.value.status_code == 403
        assert "Forbidden" in str(exc_info.value.detail)
    
    def test_raise_not_found(self):
        """Test raising not found error"""
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Not found")
        
        assert exc_info.value.status_code == 404
        assert "Not found" in str(exc_info.value.detail)
    
    def test_raise_conflict(self):
        """Test raising conflict error"""
        with pytest.raises(HTTPException) as exc_info:
            raise_conflict("Conflict")
        
        assert exc_info.value.status_code == 409
        assert "Conflict" in str(exc_info.value.detail)
    
    def test_raise_validation_error(self):
        """Test raising validation error"""
        with pytest.raises(HTTPException) as exc_info:
            raise_validation_error("Validation error")
        
        assert exc_info.value.status_code == 422
        assert "Validation error" in str(exc_info.value.detail)
    
    def test_raise_server_error(self):
        """Test raising server error"""
        with pytest.raises(HTTPException) as exc_info:
            raise_server_error("Server error")
        
        assert exc_info.value.status_code == 500
        assert "Server error" in str(exc_info.value.detail)
    
    def test_install_exception_handlers(self):
        """Test installing exception handlers"""
        app = FastAPI()
        
        install_exception_handlers(app)
        
        # Check that exception handlers are registered
        assert HTTPException in app.exception_handlers
        assert Exception in app.exception_handlers
    
    def test_error_response_with_request_id(self):
        """Test error response with request ID"""
        response = create_error_response(
            message="Test error",
            code="test_error",
            request_id="req-123"
        )
        
        assert response.request_id == "req-123"
        assert response.error.request_id == "req-123"
    
    def test_error_response_with_details(self):
        """Test error response with details"""
        response = create_error_response(
            message="Test error",
            code="test_error",
            details={"field": "value", "number": 123}
        )
        
        assert response.error.details == {"field": "value", "number": 123}