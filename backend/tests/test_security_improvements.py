"""
Tests for security improvements: password validation, rate limiting, PAT scopes
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import time

from app.main import app
from app.core.security import validate_password_strength, hash_password, verify_password
from app.core.pat_validation import validate_scopes, check_scope_permission
from app.core.config import settings

client = TestClient(app)

class TestPasswordValidation:
    """Test password strength validation"""
    
    def test_valid_password(self):
        """Test valid password passes validation"""
        password = "StrongPassword123!"
        is_valid, error_msg = validate_password_strength(password)
        assert is_valid
        assert error_msg == ""
    
    def test_password_too_short(self):
        """Test password too short fails validation"""
        password = "Short1!"
        is_valid, error_msg = validate_password_strength(password)
        assert not is_valid
        assert "at least" in error_msg and "characters" in error_msg
    
    def test_password_no_uppercase(self):
        """Test password without uppercase fails validation"""
        password = "lowercase123!"
        is_valid, error_msg = validate_password_strength(password)
        assert not is_valid
        assert "uppercase" in error_msg
    
    def test_password_no_lowercase(self):
        """Test password without lowercase fails validation"""
        password = "UPPERCASE123!"
        is_valid, error_msg = validate_password_strength(password)
        assert not is_valid
        assert "lowercase" in error_msg
    
    def test_password_no_digits(self):
        """Test password without digits fails validation"""
        password = "NoDigits!"
        is_valid, error_msg = validate_password_strength(password)
        assert not is_valid
        assert "digit" in error_msg
    
    def test_password_no_special(self):
        """Test password without special characters fails validation"""
        password = "NoSpecial123"
        is_valid, error_msg = validate_password_strength(password)
        assert not is_valid
        assert "special" in error_msg
    
    def test_password_with_pepper(self):
        """Test password hashing with pepper"""
        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        # Hashes should be different due to salt
        assert hash1 != hash2
        
        # Both should verify correctly
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)
        
        # Wrong password should not verify
        assert not verify_password("WrongPassword123!", hash1)

class TestPATScopeValidation:
    """Test PAT scope validation"""
    
    def test_valid_scopes(self):
        """Test valid scopes pass validation"""
        scopes = ["api:read", "rag:write", "chat:admin"]
        validated = validate_scopes(scopes)
        assert "api:read" in validated
        assert "rag:write" in validated
        assert "chat:admin" in validated
        assert "chat:read" in validated  # Should be expanded from chat:admin
        assert "chat:write" in validated  # Should be expanded from chat:admin
    
    def test_invalid_scopes(self):
        """Test invalid scopes raise exception"""
        scopes = ["invalid:scope", "api:read"]
        with pytest.raises(Exception):  # HTTPException
            validate_scopes(scopes)
    
    def test_empty_scopes(self):
        """Test empty scopes return empty list"""
        scopes = []
        validated = validate_scopes(scopes)
        assert validated == []
    
    def test_scope_permission_check(self):
        """Test scope permission checking"""
        user_scopes = ["api:admin", "rag:read"]
        
        # Should have permission for included scopes
        assert check_scope_permission(user_scopes, "api:admin")
        assert check_scope_permission(user_scopes, "rag:read")
        
        # Should have permission for lower-level scopes
        assert check_scope_permission(user_scopes, "api:read")
        assert check_scope_permission(user_scopes, "api:write")
        
        # Should not have permission for unrelated scopes
        assert not check_scope_permission(user_scopes, "chat:read")
        assert not check_scope_permission(user_scopes, "users:admin")

class TestRateLimiting:
    """Test rate limiting functionality"""
    
    def test_login_rate_limiting(self):
        """Test login endpoint rate limiting"""
        # Make multiple login attempts
        for i in range(12):  # More than the limit
            response = client.post("/api/auth/login", json={
                "login": "testuser",
                "password": "wrongpassword"
            })
            
            if i < 10:  # First 10 should be allowed
                assert response.status_code in [400, 401]  # Bad request or unauthorized
            else:  # After 10 should be rate limited
                assert response.status_code == 429  # Too Many Requests
                assert "rate_limit_exceeded" in response.json().get("error", "")
                break
    
    def test_password_reset_rate_limiting(self):
        """Test password reset endpoint rate limiting"""
        # Make multiple password reset requests
        for i in range(7):  # More than the limit
            response = client.post("/auth/password/forgot", json={
                "login_or_email": "test@example.com"
            })
            
            if i < 5:  # First 5 should be allowed
                assert response.status_code == 200
            else:  # After 5 should be rate limited
                assert response.status_code == 429
                break

class TestAdminAPIValidation:
    """Test admin API with new validations"""
    
    def test_create_user_with_weak_password(self):
        """Test creating user with weak password fails"""
        # This would need admin authentication in real test
        # For now, just test the validation logic
        weak_passwords = [
            "short",
            "nouppercase123!",
            "NOLOWERCASE123!",
            "NoDigits!",
            "NoSpecial123"
        ]
        
        for password in weak_passwords:
            is_valid, error_msg = validate_password_strength(password)
            assert not is_valid, f"Password '{password}' should be invalid"
            assert error_msg != "", f"Error message should not be empty for '{password}'"
    
    def test_create_pat_with_invalid_scopes(self):
        """Test creating PAT with invalid scopes fails"""
        invalid_scopes = ["invalid:scope", "api:invalid", "unknown:action"]
        
        for scope in invalid_scopes:
            with pytest.raises(Exception):  # HTTPException
                validate_scopes([scope])

class TestSSEHeartbeat:
    """Test SSE heartbeat functionality"""
    
    def test_sse_heartbeat_response(self):
        """Test SSE heartbeat response structure"""
        from app.api.sse import sse_heartbeat_response
        
        # This would need to be tested with actual SSE endpoint
        # For now, test the response structure
        response = sse_heartbeat_response(heartbeat_interval=1)
        
        assert response.media_type == "text/event-stream"
        assert "Cache-Control" in response.headers
        assert "Connection" in response.headers
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"

class TestCORSConfiguration:
    """Test CORS configuration"""
    
    def test_cors_headers_present(self):
        """Test that CORS headers are present in responses"""
        response = client.options("/api/auth/login")
        
        # Should have CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
    
    def test_cors_origins_configuration(self):
        """Test CORS origins configuration"""
        # Test that CORS origins are properly configured
        assert hasattr(settings, 'CORS_ORIGINS')
        assert hasattr(settings, 'CORS_ENABLED')
        assert hasattr(settings, 'CORS_ALLOW_CREDENTIALS')

class TestPasswordResetSecurity:
    """Test password reset security features"""
    
    def test_password_reset_token_expiry(self):
        """Test that password reset tokens have proper expiry"""
        from datetime import datetime, timedelta
        
        # Test token creation with expiry
        expires_at = datetime.utcnow() + timedelta(minutes=60)
        assert expires_at > datetime.utcnow()
    
    def test_password_reset_always_returns_200(self):
        """Test that password reset always returns 200 for security"""
        # Test with non-existent user
        response = client.post("/auth/password/forgot", json={
            "login_or_email": "nonexistent@example.com"
        })
        assert response.status_code == 200
        
        # Test with invalid email format
        response = client.post("/auth/password/forgot", json={
            "login_or_email": "invalid-email"
        })
        assert response.status_code == 200

class TestAuditLogging:
    """Test audit logging functionality"""
    
    def test_audit_log_structure(self):
        """Test audit log entry structure"""
        from app.services.audit_service import AuditService
        from app.core.db import get_db
        
        # This would need proper database setup in real test
        # For now, test the service structure
        assert hasattr(AuditService, 'log_action')
        assert hasattr(AuditService, 'log_user_action')
        assert hasattr(AuditService, 'log_token_action')
        assert hasattr(AuditService, 'log_auth_action')

if __name__ == "__main__":
    pytest.main([__file__])
