"""
Simple unit tests for admin router
"""
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException, status

from app.api.routers.admin import (
    create_error_response, user_to_response
)
from app.models.user import Users


class TestAdminRouterSimple:
    """Test admin router functions - simple version"""
    
    def setup_method(self):
        """Setup test method"""
        # Mock user data
        self.mock_user = Mock(spec=Users)
        self.mock_user.id = "user123"
        self.mock_user.login = "testuser"
        self.mock_user.email = "test@example.com"
        self.mock_user.role = "reader"
        self.mock_user.is_active = True
        self.mock_user.created_at = "2023-01-01T00:00:00"
        self.mock_user.updated_at = "2023-01-01T00:00:00"
    
    def test_create_error_response(self):
        """Test create_error_response function"""
        result = create_error_response("TEST_ERROR", "Test message", "req123", {"key": "value"})
        
        expected = {
            "error": {
                "code": "TEST_ERROR",
                "message": "Test message",
                "details": {"key": "value"}
            },
            "request_id": "req123"
        }
        assert result == expected
    
    def test_create_error_response_no_details(self):
        """Test create_error_response without details"""
        result = create_error_response("TEST_ERROR", "Test message", "req123")
        
        expected = {
            "error": {
                "code": "TEST_ERROR",
                "message": "Test message",
                "details": {}
            },
            "request_id": "req123"
        }
        assert result == expected
    
    def test_user_to_response(self):
        """Test user_to_response function"""
        result = user_to_response(self.mock_user)
        
        assert result.id == "user123"
        assert result.login == "testuser"
        assert result.email == "test@example.com"
        assert result.role == "reader"
        assert result.is_active is True
