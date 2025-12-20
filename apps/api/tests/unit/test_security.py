"""
Unit tests for core security functions (password hashing, JWT)
"""
import pytest
from unittest.mock import patch, MagicMock
import time

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_jwt,
    UserCtx,
)


class TestPasswordHashing:
    """Test password hashing and verification with argon2"""
    
    def test_hash_password_returns_string(self):
        """hash_password should return a string hash"""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password  # Should not be plaintext
    
    def test_hash_password_different_each_time(self):
        """Same password should produce different hashes (salt)"""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2  # Argon2 uses random salt
    
    def test_verify_password_correct(self):
        """verify_password should return True for correct password"""
        password = "correct_password_456"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        """verify_password should return False for wrong password"""
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_verify_password_empty_password(self):
        """verify_password should handle empty password"""
        password = "some_password"
        hashed = hash_password(password)
        
        assert verify_password("", hashed) is False
    
    def test_verify_password_invalid_hash(self):
        """verify_password should return False for invalid hash format"""
        assert verify_password("password", "invalid_hash_format") is False
    
    def test_verify_password_none_hash(self):
        """verify_password should handle None hash gracefully"""
        # This should not raise, just return False
        try:
            result = verify_password("password", None)
            assert result is False
        except (TypeError, AttributeError):
            # Also acceptable - type error on None
            pass
    
    def test_hash_password_special_characters(self):
        """hash_password should handle special characters"""
        password = "p@$$w0rd!#$%^&*()_+-=[]{}|;':\",./<>?"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_hash_password_unicode(self):
        """hash_password should handle unicode characters"""
        password = "пароль密码🔐"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_hash_password_long_password(self):
        """hash_password should handle very long passwords"""
        password = "a" * 1000  # 1000 character password
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True


class TestJWT:
    """Test JWT token creation and validation"""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for JWT tests"""
        settings = MagicMock()
        settings.JWT_SECRET = "test-secret-key-for-testing-only"
        settings.JWT_ALGORITHM = "HS256"
        settings.JWT_ISSUER = "test-issuer"
        settings.JWT_AUDIENCE = "test-audience"
        settings.JWT_ACCESS_TTL_MINUTES = 15
        settings.JWT_REFRESH_TTL_DAYS = 30
        settings.JWT_KID = None
        settings.JWT_PRIVATE_KEY = None
        settings.JWT_PUBLIC_KEY = None
        settings.PASSWORD_PEPPER = ""
        return settings
    
    def test_create_access_token(self, mock_settings):
        """create_access_token should return valid JWT string"""
        with patch('app.core.security.get_settings', return_value=mock_settings):
            token = create_access_token(
                user_id="user-123",
                email="test@example.com",
                role="admin",
                tenant_ids=["tenant-1", "tenant-2"],
                scopes=["read", "write"]
            )
            
            assert isinstance(token, str)
            assert len(token) > 0
            # JWT has 3 parts separated by dots
            assert len(token.split('.')) == 3
    
    def test_create_refresh_token(self, mock_settings):
        """create_refresh_token should return valid JWT string"""
        with patch('app.core.security.get_settings', return_value=mock_settings):
            token = create_refresh_token(user_id="user-123")
            
            assert isinstance(token, str)
            assert len(token.split('.')) == 3
    
    def test_decode_jwt_valid_token(self, mock_settings):
        """decode_jwt should decode valid access token"""
        with patch('app.core.security.get_settings', return_value=mock_settings):
            token = create_access_token(
                user_id="user-456",
                email="decode@test.com",
                role="reader",
                tenant_ids=["t1"],
                scopes=[]
            )
            
            payload = decode_jwt(token)
            
            assert payload["sub"] == "user-456"
            assert payload["email"] == "decode@test.com"
            assert payload["role"] == "reader"
            assert payload["tenant_ids"] == ["t1"]
            assert payload["type"] == "access"
    
    def test_decode_jwt_expired_token(self, mock_settings):
        """decode_jwt should raise for expired token"""
        from fastapi import HTTPException
        
        # Set TTL to 0 to create expired token
        mock_settings.JWT_ACCESS_TTL_MINUTES = 0
        
        with patch('app.core.security.get_settings', return_value=mock_settings):
            token = create_access_token(
                user_id="user-789",
                email="expired@test.com",
                role="reader",
                tenant_ids=[],
                scopes=[]
            )
            
            # Token is already expired (TTL=0)
            with pytest.raises(HTTPException) as exc_info:
                decode_jwt(token)
            
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()
    
    def test_decode_jwt_invalid_token(self, mock_settings):
        """decode_jwt should raise for invalid token"""
        from fastapi import HTTPException
        
        with patch('app.core.security.get_settings', return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                decode_jwt("invalid.token.here")
            
            assert exc_info.value.status_code == 401
    
    def test_access_token_contains_required_claims(self, mock_settings):
        """Access token should contain all required claims"""
        with patch('app.core.security.get_settings', return_value=mock_settings):
            token = create_access_token(
                user_id="claim-test-user",
                email="claims@test.com",
                role="editor",
                tenant_ids=["t1", "t2"],
                scopes=["rag:read", "rag:write"]
            )
            
            payload = decode_jwt(token)
            
            # Required claims
            assert "sub" in payload
            assert "email" in payload
            assert "role" in payload
            assert "tenant_ids" in payload
            assert "scopes" in payload
            assert "iss" in payload
            assert "aud" in payload
            assert "iat" in payload
            assert "exp" in payload
            assert "jti" in payload
            assert "type" in payload
            
            # Verify values
            assert payload["iss"] == "test-issuer"
            assert payload["aud"] == "test-audience"
            assert payload["type"] == "access"
    
    def test_refresh_token_contains_minimal_claims(self, mock_settings):
        """Refresh token should contain minimal claims"""
        with patch('app.core.security.get_settings', return_value=mock_settings):
            token = create_refresh_token(user_id="refresh-user")
            payload = decode_jwt(token)
            
            assert payload["sub"] == "refresh-user"
            assert payload["type"] == "refresh"
            # Refresh token should NOT contain sensitive data
            assert "email" not in payload
            assert "role" not in payload


class TestUserCtx:
    """Test UserCtx dataclass"""
    
    def test_user_ctx_creation(self):
        """UserCtx should be created with all fields"""
        ctx = UserCtx(
            id="user-id-123",
            email="user@example.com",
            role="admin",
            tenant_ids=["t1", "t2"],
            scopes=["read", "write"]
        )
        
        assert ctx.id == "user-id-123"
        assert ctx.email == "user@example.com"
        assert ctx.role == "admin"
        assert ctx.tenant_ids == ["t1", "t2"]
        assert ctx.scopes == ["read", "write"]
    
    def test_user_ctx_defaults(self):
        """UserCtx should have sensible defaults"""
        ctx = UserCtx(id="minimal-user")
        
        assert ctx.id == "minimal-user"
        assert ctx.email is None
        assert ctx.role == "reader"
        assert ctx.tenant_ids is None
        assert ctx.scopes is None
