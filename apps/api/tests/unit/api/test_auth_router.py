"""
Unit tests for auth router
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.routers.auth import login, refresh, me, logout
from app.models.user import Users


class TestAuthRouter:
    """Test auth router functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock(spec=Session)
        self.mock_request = Mock()
        self.mock_response = Mock()
        
        # Mock user data
        self.mock_user = Mock(spec=Users)
        self.mock_user.id = "user123"
        self.mock_user.login = "testuser"
        self.mock_user.role = "reader"
        self.mock_user.fio = "Test User"
        self.mock_user.is_active = True
    
    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful login"""
        payload = {"login": "testuser", "password": "password123"}
        
        with patch('app.api.routers.auth.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.auth.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.auth.UsersService') as mock_service_class, \
             patch('app.core.security.encode_jwt') as mock_encode_jwt:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.authenticate_user.return_value = self.mock_user
            mock_encode_jwt.side_effect = ["access_token", "refresh_token"]
            
            # Call function
            result = await login(self.mock_request, payload, self.mock_session)
            
            # Assertions
            assert result["access_token"] == "access_token"
            assert result["refresh_token"] == "refresh_token"
            assert result["token_type"] == "bearer"
            assert result["expires_in"] == 3600
            assert result["user"]["id"] == "user123"
            assert result["user"]["login"] == "testuser"
            assert result["user"]["role"] == "reader"
            
            # Verify calls
            mock_rate_limit.assert_called_once()
            mock_service.authenticate_user.assert_called_once_with("testuser", "password123")
            assert mock_encode_jwt.call_count == 2
    
    @pytest.mark.asyncio
    async def test_login_missing_credentials(self):
        """Test login with missing credentials"""
        payload = {"login": "", "password": ""}
        
        with patch('app.api.routers.auth.rate_limit', new_callable=AsyncMock) as mock_rate_limit:
            mock_rate_limit.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                await login(self.mock_request, payload, self.mock_session)
            
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert exc_info.value.detail == "missing_credentials"
    
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        payload = {"login": "testuser", "password": "wrongpassword"}
        
        with patch('app.api.routers.auth.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.auth.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.auth.UsersService') as mock_service_class:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.authenticate_user.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                await login(self.mock_request, payload, self.mock_session)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "invalid_credentials"
    
    @pytest.mark.asyncio
    async def test_login_value_error(self):
        """Test login with ValueError from service"""
        payload = {"login": "testuser", "password": "password123"}
        
        with patch('app.api.routers.auth.rate_limit', new_callable=AsyncMock) as mock_rate_limit, \
             patch('app.api.routers.auth.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.auth.UsersService') as mock_service_class:
            
            # Setup mocks
            mock_rate_limit.return_value = None
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.authenticate_user.side_effect = ValueError("Invalid credentials")
            
            with pytest.raises(HTTPException) as exc_info:
                await login(self.mock_request, payload, self.mock_session)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "invalid_credentials"
    
    @pytest.mark.asyncio
    async def test_refresh_success(self):
        """Test successful token refresh"""
        payload = {"refresh_token": "valid_refresh_token"}
        
        with patch('app.core.security.decode_jwt') as mock_decode_jwt, \
             patch('app.api.routers.auth.UsersRepository') as mock_repo_class, \
             patch('app.core.security.encode_jwt') as mock_encode_jwt:
            
            # Setup mocks
            mock_decode_jwt.return_value = {
                "sub": "user123",
                "user_id": "user123",
                "role": "reader"
            }
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = self.mock_user
            mock_encode_jwt.return_value = "new_access_token"
            
            # Call function
            result = await refresh(payload, self.mock_session)
            
            # Assertions
            assert result["access_token"] == "new_access_token"
            assert result["refresh_token"] == "valid_refresh_token"
            assert result["token_type"] == "bearer"
            assert result["expires_in"] == 3600
            
            # Verify calls
            mock_decode_jwt.assert_called_once_with("valid_refresh_token")
            mock_repo.get_by_id.assert_called_once_with("user123")
            mock_encode_jwt.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_refresh_missing_token(self):
        """Test refresh with missing token"""
        payload = {}
        
        with pytest.raises(HTTPException) as exc_info:
            await refresh(payload, self.mock_session)
        
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "missing_refresh_token"
    
    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self):
        """Test refresh with invalid token"""
        payload = {"refresh_token": "invalid_token"}
        
        with patch('app.core.security.decode_jwt') as mock_decode_jwt:
            mock_decode_jwt.side_effect = ValueError("Invalid token")
            
            with pytest.raises(HTTPException) as exc_info:
                await refresh(payload, self.mock_session)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "Invalid token"
    
    @pytest.mark.asyncio
    async def test_refresh_user_not_found(self):
        """Test refresh with user not found"""
        payload = {"refresh_token": "valid_token"}
        
        with patch('app.core.security.decode_jwt') as mock_decode_jwt, \
             patch('app.api.routers.auth.UsersRepository') as mock_repo_class:
            
            # Setup mocks
            mock_decode_jwt.return_value = {
                "sub": "user123",
                "user_id": "user123",
                "role": "reader"
            }
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                await refresh(payload, self.mock_session)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "User not found or inactive"
    
    @pytest.mark.asyncio
    async def test_refresh_inactive_user(self):
        """Test refresh with inactive user"""
        payload = {"refresh_token": "valid_token"}
        inactive_user = Mock(spec=Users)
        inactive_user.id = "user123"
        inactive_user.is_active = False
        
        with patch('app.core.security.decode_jwt') as mock_decode_jwt, \
             patch('app.api.routers.auth.UsersRepository') as mock_repo_class:
            
            # Setup mocks
            mock_decode_jwt.return_value = {
                "sub": "user123",
                "user_id": "user123",
                "role": "reader"
            }
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get_by_id.return_value = inactive_user
            
            with pytest.raises(HTTPException) as exc_info:
                await refresh(payload, self.mock_session)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "User not found or inactive"
    
    def test_me_success(self):
        """Test me endpoint with valid user"""
        mock_user = {"id": "user123", "login": "testuser", "role": "reader"}
        
        result = me(mock_user)
        
        assert result == mock_user
    
    @pytest.mark.asyncio
    async def test_logout_with_token(self):
        """Test logout with refresh token"""
        payload = {"refresh_token": "valid_token"}
        
        with patch('app.api.routers.auth.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.auth.UsersService') as mock_service_class, \
             patch('app.api.routers.auth.Response') as mock_response_class:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.revoke_token = AsyncMock()
            mock_response = Mock()
            mock_response_class.return_value = mock_response
            
            # Call function
            result = await logout(payload, self.mock_session)
            
            # Assertions
            assert result == mock_response
            mock_service.revoke_token.assert_called_once_with("valid_token")
    
    @pytest.mark.asyncio
    async def test_logout_without_token(self):
        """Test logout without refresh token"""
        payload = None
        
        with patch('app.api.routers.auth.Response') as mock_response_class:
            # Setup mocks
            mock_response = Mock()
            mock_response_class.return_value = mock_response
            
            # Call function
            result = await logout(payload, self.mock_session)
            
            # Assertions
            assert result == mock_response
    
    @pytest.mark.asyncio
    async def test_logout_with_empty_payload(self):
        """Test logout with empty payload"""
        payload = {}
        
        with patch('app.api.routers.auth.Response') as mock_response_class:
            # Setup mocks
            mock_response = Mock()
            mock_response_class.return_value = mock_response
            
            # Call function
            result = await logout(payload, self.mock_session)
            
            # Assertions
            assert result == mock_response
