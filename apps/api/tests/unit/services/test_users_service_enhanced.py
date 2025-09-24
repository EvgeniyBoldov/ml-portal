"""
Unit tests for users service enhanced
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from app.services.users_service_enhanced import UsersService, AsyncUsersService
from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens


class TestUsersServiceEnhanced:
    """Test users service enhanced functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.mock_service = UsersService(self.mock_session)
        
        # Mock user data
        self.mock_user = Mock(spec=Users)
        self.mock_user.id = "user123"
        self.mock_user.login = "testuser"
        self.mock_user.email = "test@example.com"
        self.mock_user.role = "reader"
        self.mock_user.is_active = True
        self.mock_user.password_hash = "hashed_password"
        self.mock_user.created_at = datetime.now(timezone.utc)
        self.mock_user.updated_at = datetime.now(timezone.utc)
    
    def test_get_required_fields(self):
        """Test _get_required_fields method"""
        result = self.mock_service._get_required_fields()
        assert result == ["login", "password_hash"]
    
    def test_sanitize_string(self):
        """Test _sanitize_string method"""
        # Test normal string
        result = self.mock_service._sanitize_string("  Test String  ", 100)
        assert result == "Test String"
        
        # Test string too long
        long_string = "a" * 150
        result = self.mock_service._sanitize_string(long_string, 100)
        assert len(result) == 100
        assert result == "a" * 100
        
        # Test None input
        result = self.mock_service._sanitize_string(None, 100)
        assert result is None
        
        # Test empty string
        result = self.mock_service._sanitize_string("", 100)
        assert result == ""
    
    def test_process_create_data(self):
        """Test _process_create_data method"""
        # Valid data
        valid_data = {
            "login": "  TestUser  ",
            "password_hash": "hashed_password",
            "email": "  test@example.com  ",
            "role": "reader"
        }
        result = self.mock_service._process_create_data(valid_data)
        assert result["login"] == "testuser"  # Should be lowercased and trimmed
        assert result["email"] == "test@example.com"  # Should be trimmed
        assert result["password_hash"] == "hashed_password"
    
    def test_hash_password(self):
        """Test _hash_password method"""
        password = "testpassword"
        result = self.mock_service._hash_password(password)
        
        # Should return a hashed string
        assert isinstance(result, str)
        assert len(result) > 0
        assert result != password
    
    def test_verify_password(self):
        """Test _verify_password method"""
        password = "testpassword"
        hashed = self.mock_service._hash_password(password)
        
        # Should verify correctly
        assert self.mock_service._verify_password(password, hashed) is True
        assert self.mock_service._verify_password("wrongpassword", hashed) is False
    
    def test_create_user_success(self):
        """Test create_user method success"""
        with patch.object(self.mock_service, '_validate_user_data') as mock_validate, \
             patch.object(self.mock_service, '_hash_password') as mock_hash, \
             patch.object(self.mock_service.users_repo, 'create_user') as mock_create:
            
            # Setup mocks
            mock_validate.return_value = True
            mock_hash.return_value = "hashed_password"
            mock_create.return_value = self.mock_user
            
            # Call method
            result = self.mock_service.create_user(
                login="testuser",
                password="testpassword",
                role="reader",
                email="test@example.com"
            )
            
            # Assertions
            assert result == self.mock_user
            mock_hash.assert_called_once_with("testpassword")
            mock_create.assert_called_once()
    
    
    def test_authenticate_user_success(self):
        """Test successful user authentication"""
        login = "testuser"
        password = "password123"
        
        with patch.object(self.mock_service.users_repo, 'get_by_login') as mock_get_by_login, \
             patch.object(self.mock_service, '_verify_password') as mock_verify_password:
            
            # Setup mocks
            mock_get_by_login.return_value = self.mock_user
            mock_verify_password.return_value = True
            
            # Call function
            result = self.mock_service.authenticate_user(login, password)
            
            # Assertions
            assert result == self.mock_user
            
            # Verify calls
            mock_get_by_login.assert_called_once_with(login)
            mock_verify_password.assert_called_once_with(password, self.mock_user.password_hash)
    
    def test_authenticate_user_invalid_credentials(self):
        """Test user authentication with invalid credentials"""
        login = "testuser"
        password = "wrongpassword"
        
        with patch.object(self.mock_service.users_repo, 'get_by_login') as mock_get_by_login, \
             patch.object(self.mock_service, '_verify_password') as mock_verify_password:
            
            # Setup mocks
            mock_get_by_login.return_value = self.mock_user
            mock_verify_password.return_value = False
            
            # Call function
            result = self.mock_service.authenticate_user(login, password)
            
            # Assertions
            assert result is None
            
            # Verify calls
            mock_get_by_login.assert_called_once_with(login)
            mock_verify_password.assert_called_once_with(password, self.mock_user.password_hash)
    
    def test_authenticate_user_not_found(self):
        """Test user authentication with user not found"""
        login = "nonexistent"
        password = "password123"
        
        with patch.object(self.mock_service.users_repo, 'get_by_login') as mock_get_by_login:
            # Setup mocks
            mock_get_by_login.return_value = None
            
            # Call function
            result = self.mock_service.authenticate_user(login, password)
            
            # Assertions
            assert result is None
            
            # Verify calls
            mock_get_by_login.assert_called_once_with(login)
    
    def test_update_user_password(self):
        """Test user password update"""
        user_id = "user123"
        new_password = "newpassword123"
        
        with patch.object(self.mock_service.users_repo, 'get_by_id') as mock_get_by_id, \
             patch.object(self.mock_service, '_hash_password') as mock_hash_password, \
             patch.object(self.mock_service.users_repo, 'update_user') as mock_update_user:
            
            # Setup mocks
            mock_get_by_id.return_value = self.mock_user
            mock_hash_password.return_value = "new_hashed_password"
            mock_update_user.return_value = self.mock_user
            
            # Call function
            result = self.mock_service.update_user_password(user_id, new_password)
            
            # Assertions
            assert result == self.mock_user
            
            # Verify calls
            mock_get_by_id.assert_called_once_with(user_id)
            mock_hash_password.assert_called_once_with(new_password)
            mock_update_user.assert_called_once()
    
    def test_deactivate_user(self):
        """Test user deactivation"""
        user_id = "user123"
        
        with patch.object(self.mock_service.users_repo, 'get_by_id') as mock_get_by_id, \
             patch.object(self.mock_service.users_repo, 'update_user') as mock_update_user:
            
            # Setup mocks
            mock_get_by_id.return_value = self.mock_user
            mock_update_user.return_value = self.mock_user
            
            # Call function
            result = self.mock_service.deactivate_user(user_id)
            
            # Assertions
            assert result == self.mock_user
            
            # Verify calls
            mock_get_by_id.assert_called_once_with(user_id)
            mock_update_user.assert_called_once()
    
    def test_get_user_by_login(self):
        """Test get user by login"""
        login = "testuser"
        
        with patch.object(self.mock_service.users_repo, 'get_by_login') as mock_get_by_login:
            # Setup mocks
            mock_get_by_login.return_value = self.mock_user
            
            # Call function
            result = self.mock_service.get_user_by_login(login)
            
            # Assertions
            assert result == self.mock_user
            
            # Verify calls
            mock_get_by_login.assert_called_once_with(login)
    
    def test_get_user_by_email(self):
        """Test get user by email"""
        email = "test@example.com"
        
        with patch.object(self.mock_service.users_repo, 'get_by_email') as mock_get_by_email:
            # Setup mocks
            mock_get_by_email.return_value = self.mock_user
            
            # Call function
            result = self.mock_service.get_user_by_email(email)
            
            # Assertions
            assert result == self.mock_user
            
            # Verify calls
            mock_get_by_email.assert_called_once_with(email)
