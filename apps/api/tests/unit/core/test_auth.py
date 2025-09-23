"""
Unit tests for authentication core components
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.core.auth import UserCtx, get_current_user
from app.api.deps import require_user, require_admin


class TestUserCtx:
    """Test UserCtx class"""
    
    def test_user_ctx_creation(self):
        """Test creating UserCtx"""
        user = UserCtx(id="user123", role="reader")
        
        assert user.id == "user123"
        assert user.role == "reader"
    
    def test_user_ctx_str_representation(self):
        """Test UserCtx string representation"""
        user = UserCtx(id="user123", role="reader")
        
        assert "user123" in str(user)
        assert "reader" in str(user)
    
    def test_user_ctx_defaults(self):
        """Test UserCtx default values"""
        user = UserCtx(id="user123")
        
        assert user.id == "user123"
        assert user.role == "reader"  # Default role


class TestAuthFunctions:
    """Test authentication functions"""
    
    def test_get_current_user_mock(self):
        """Test get_current_user function"""
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer test-token"}
        
        with patch('app.core.auth.decode_token') as mock_decode:
            mock_decode.return_value = {"sub": "user123", "role": "reader"}
            result = get_current_user(mock_request)
            
            assert result.id == "user123"
            assert result.role == "reader"
    
    def test_require_user_mock(self):
        """Test require_user function"""
        mock_user = UserCtx(id="user123", role="reader")
        
        # require_user is a dependency function, so we need to call it with the user
        result = require_user(mock_user)
        
        assert result.id == "user123"
        assert result.role == "reader"
    
    def test_require_admin_mock(self):
        """Test require_admin function"""
        mock_admin = UserCtx(id="admin123", role="admin")
        
        # require_admin is a dependency function, so we need to call it with the admin user
        result = require_admin(mock_admin)
        
        assert result.id == "admin123"
        assert result.role == "admin"
    
    def test_user_roles(self):
        """Test different user roles"""
        # Reader role
        reader = UserCtx(id="user1", role="reader")
        assert reader.role == "reader"
        
        # Editor role
        editor = UserCtx(id="user2", role="editor")
        assert editor.role == "editor"
        
        # Admin role
        admin = UserCtx(id="user3", role="admin")
        assert admin.role == "admin"
    
    def test_user_ctx_equality(self):
        """Test UserCtx equality"""
        user1 = UserCtx(id="user123", role="reader")
        user2 = UserCtx(id="user123", role="reader")
        user3 = UserCtx(id="user456", role="reader")
        
        assert user1 == user2
        assert user1 != user3