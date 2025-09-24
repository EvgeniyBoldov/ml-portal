"""
Unit tests for password reset router
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException, status

from app.api.routers.password_reset import create_error_response, forgot_password, reset_password
from app.models.user import Users
from app.api.schemas.users import PasswordResetRequest, PasswordResetConfirm


class TestPasswordResetRouter:
    """Test password reset router functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.mock_request = Mock()
        
        # Mock user data
        self.mock_user = Mock(spec=Users)
        self.mock_user.id = "user123"
        self.mock_user.login = "testuser"
        self.mock_user.email = "test@example.com"
        self.mock_user.is_active = True
        self.mock_user.refresh_tokens = []  # Empty list for iteration
    
    def test_create_error_response(self):
        """Test create_error_response function"""
        result = create_error_response("TEST_ERROR", "Test message", "req123", {"key": "value"})
        
        assert result.error == "TEST_ERROR"
        assert result.message == "Test message"
        assert result.request_id == "req123"
        assert result.details == {"key": "value"}
    
    def test_create_error_response_no_details(self):
        """Test create_error_response without details"""
        result = create_error_response("TEST_ERROR", "Test message", "req123")
        
        assert result.error == "TEST_ERROR"
        assert result.message == "Test message"
        assert result.request_id == "req123"
        assert result.details is None
    
    @pytest.mark.asyncio
    async def test_forgot_password_user_found_by_login(self):
        """Test forgot password with user found by login"""
        request_data = PasswordResetRequest(login_or_email="testuser")
        
        with patch('app.api.routers.password_reset.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.password_reset.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.password_reset.AuditService') as mock_audit_class, \
             patch('app.api.routers.password_reset.secrets') as mock_secrets, \
             patch('app.api.routers.password_reset.hash_password') as mock_hash_password:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.by_login.return_value = self.mock_user
            mock_audit = Mock()
            mock_audit_class.return_value = mock_audit
            mock_audit.log_action = AsyncMock()
            mock_secrets.token_urlsafe.return_value = "reset_token_123"
            mock_hash_password.return_value = "hashed_token"
            
            # Call function
            result = await forgot_password(request_data, self.mock_session, self.mock_request, "req123")
            
            # Assertions
            assert result["message"] == "If the account exists, a password reset link has been sent"
            
            # Verify calls
            mock_rate_limit.assert_called_once()
            mock_repo.by_login.assert_called_once_with("testuser")
    
    @pytest.mark.asyncio
    async def test_forgot_password_user_found_by_email(self):
        """Test forgot password with user found by email"""
        request_data = PasswordResetRequest(login_or_email="test@example.com")
        
        with patch('app.api.routers.password_reset.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.password_reset.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.password_reset.AuditService') as mock_audit_class, \
             patch('app.api.routers.password_reset.secrets') as mock_secrets, \
             patch('app.api.routers.password_reset.hash_password') as mock_hash_password:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.by_login.return_value = None  # Not found by login
            mock_repo.s.execute.return_value.scalars.return_value.all.return_value = [self.mock_user]
            mock_audit = Mock()
            mock_audit_class.return_value = mock_audit
            mock_audit.log_action = AsyncMock()
            mock_secrets.token_urlsafe.return_value = "reset_token_123"
            mock_hash_password.return_value = "hashed_token"
            
            # Call function
            result = await forgot_password(request_data, self.mock_session, self.mock_request, "req123")
            
            # Assertions
            assert result["message"] == "If the account exists, a password reset link has been sent"
            
            # Verify calls
            mock_rate_limit.assert_called_once()
            mock_repo.by_login.assert_called_once_with("test@example.com")
    
    @pytest.mark.asyncio
    async def test_forgot_password_user_not_found(self):
        """Test forgot password with user not found"""
        request_data = PasswordResetRequest(login_or_email="nonexistent")
        
        with patch('app.api.routers.password_reset.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.password_reset.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.password_reset.AuditService') as mock_audit_class:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.by_login.return_value = None
            mock_repo.s.execute.return_value.scalars.return_value.all.return_value = []
            mock_audit = Mock()
            mock_audit_class.return_value = mock_audit
            mock_audit.log_action = AsyncMock()
            
            # Call function
            result = await forgot_password(request_data, self.mock_session, self.mock_request, "req123")
            
            # Assertions
            assert result["message"] == "If the account exists, a password reset link has been sent"
            
            # Verify calls
            mock_rate_limit.assert_called_once()
            mock_repo.by_login.assert_called_once_with("nonexistent")
            # Should not log audit action for non-existent user
    
    @pytest.mark.asyncio
    async def test_reset_password_success(self):
        """Test successful password reset"""
        request_data = PasswordResetConfirm(token="valid_token", new_password="NewPassword123")
        
        with patch('app.api.routers.password_reset.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.password_reset.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.password_reset.PasswordResetTokensRepository') as mock_reset_repo_class, \
             patch('app.api.routers.password_reset.AuditService') as mock_audit_class, \
             patch('app.api.routers.password_reset.validate_password_strength') as mock_validate_password, \
             patch('app.api.routers.password_reset.hash_password') as mock_hash_password, \
             patch('app.api.routers.password_reset.secrets') as mock_secrets:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_user
            mock_reset_repo = Mock()
            mock_reset_repo_class.return_value = mock_reset_repo
            # Create mock reset token object
            mock_reset_token = Mock()
            mock_reset_token.user_id = "user123"
            mock_reset_repo.get_by_hash.return_value = mock_reset_token
            mock_audit = Mock()
            mock_audit_class.return_value = mock_audit
            mock_audit.log_action = AsyncMock()
            mock_validate_password.return_value = (True, None)
            mock_hash_password.return_value = "new_hashed_password"
            mock_secrets.token_urlsafe.return_value = "new_token"
            
            # Call function
            result = await reset_password(request_data, self.mock_session, self.mock_request, "req123")
            
            # Assertions
            assert result["message"] == "Password reset successfully"
            
            # Verify calls
            mock_rate_limit.assert_called_once()
            mock_validate_password.assert_called_once_with("NewPassword123")
            # Token hash is computed from the input token
            import hashlib
            expected_hash = hashlib.sha256("valid_token".encode()).hexdigest()
            mock_reset_repo.get_by_hash.assert_called_once_with(expected_hash)
    
    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self):
        """Test password reset with invalid token"""
        request_data = PasswordResetConfirm(token="invalid_token", new_password="NewPassword123")
        
        with patch('app.api.routers.password_reset.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.password_reset.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.password_reset.PasswordResetTokensRepository') as mock_reset_repo_class, \
             patch('app.api.routers.password_reset.validate_password_strength') as mock_validate_password:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_reset_repo = Mock()
            mock_reset_repo_class.return_value = mock_reset_repo
            mock_reset_repo.get_by_hash.return_value = None
            mock_validate_password.return_value = (True, None)
            
            with pytest.raises(HTTPException) as exc_info:
                await reset_password(request_data, self.mock_session, self.mock_request, "req123")
            
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert exc_info.value.detail["message"] == "Invalid or expired reset token"
    
    @pytest.mark.asyncio
    async def test_reset_password_weak_password(self):
        """Test password reset with weak password"""
        request_data = PasswordResetConfirm(token="valid_token", new_password="Weakpass1")
        
        with patch('app.api.routers.password_reset.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.password_reset.PasswordResetTokensRepository') as mock_reset_repo_class, \
             patch('app.api.routers.password_reset.validate_password_strength') as mock_validate_password:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_reset_repo = Mock()
            mock_reset_repo_class.return_value = mock_reset_repo
            # Create mock reset token object
            mock_reset_token = Mock()
            mock_reset_token.user_id = "user123"
            mock_reset_repo.get_by_hash.return_value = mock_reset_token
            mock_validate_password.return_value = (False, "Password too weak")
            
            with pytest.raises(HTTPException) as exc_info:
                await reset_password(request_data, self.mock_session, self.mock_request, "req123")
            
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "Password validation failed: Password too weak" in exc_info.value.detail["message"]
