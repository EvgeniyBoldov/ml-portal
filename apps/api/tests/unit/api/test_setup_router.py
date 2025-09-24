"""
Unit tests for setup router
"""
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException

from app.api.routers.setup import create_superuser, setup_status
from app.models.user import Users


class TestSetupRouter:
    """Test setup router functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        
        # Mock admin user
        self.mock_admin_user = Mock(spec=Users)
        self.mock_admin_user.id = "admin123"
        self.mock_admin_user.login = "admin"
        self.mock_admin_user.email = "admin@test.com"
        self.mock_admin_user.role = "admin"
        self.mock_admin_user.is_active = True
        self.mock_admin_user.created_at = "2023-01-01T00:00:00"
        self.mock_admin_user.updated_at = "2023-01-01T00:00:00"
        self.mock_admin_user.require_password_change = False
    
    @pytest.mark.asyncio
    async def test_create_superuser_success(self):
        """Test successful superuser creation"""
        with patch('app.core.config.settings') as mock_settings, \
             patch('app.api.routers.setup.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.setup.hash_password') as mock_hash_password:
            
            # Setup mocks
            mock_settings.DEBUG = True
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.create_user.return_value = self.mock_admin_user
            mock_hash_password.return_value = "hashed_password"
            
            # Mock session query
            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = None  # No existing admin
            self.mock_session.query.return_value = mock_query
            
            # Call function
            result = await create_superuser(
                login="admin",
                password="admin123456",
                email="admin@test.com",
                session=self.mock_session
            )
            
            # Assertions
            assert result.id == "admin123"
            assert result.login == "admin"
            assert result.email == "admin@test.com"
            assert result.role == "admin"
            assert result.is_active is True
            
            # Verify calls
            mock_repo.create_user.assert_called_once()
            mock_hash_password.assert_called_once_with("admin123456")
    
    @pytest.mark.asyncio
    async def test_create_superuser_not_debug_mode(self):
        """Test superuser creation when not in debug mode"""
        with patch('app.api.routers.setup.settings') as mock_settings:
            # Setup mocks
            mock_settings.DEBUG = False
            
            with pytest.raises(HTTPException) as exc_info:
                await create_superuser(session=self.mock_session)
            
            assert exc_info.value.status_code == 403
            assert "Setup endpoints only available in debug mode" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_create_superuser_admin_exists(self):
        """Test superuser creation when admin already exists"""
        with patch('app.api.routers.setup.settings') as mock_settings:
            # Setup mocks
            mock_settings.DEBUG = True
            
            # Mock session query - admin exists
            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = self.mock_admin_user
            self.mock_session.query.return_value = mock_query
            
            with pytest.raises(HTTPException) as exc_info:
                await create_superuser(login="admin", session=self.mock_session)
            
            assert exc_info.value.status_code == 400
            assert "User 'admin' already exists" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_create_superuser_repository_error(self):
        """Test superuser creation with repository error"""
        with patch('app.core.config.settings') as mock_settings, \
             patch('app.api.routers.setup.UsersRepository') as mock_repo_class, \
             patch('app.api.routers.setup.hash_password') as mock_hash_password:
            
            # Setup mocks
            mock_settings.DEBUG = True
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.create_user.side_effect = Exception("Database error")
            mock_hash_password.return_value = "hashed_password"
            
            # Mock session query
            mock_query = Mock()
            mock_query.filter.return_value.first.return_value = None
            self.mock_session.query.return_value = mock_query
            
            with pytest.raises(HTTPException) as exc_info:
                await create_superuser(session=self.mock_session)
            
            assert exc_info.value.status_code == 500
            assert "Failed to create superuser" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_setup_status_success(self):
        """Test successful setup status check"""
        with patch('app.api.routers.setup.settings') as mock_settings:
            # Setup mocks
            mock_settings.DEBUG = True
            
            # Mock session query
            mock_query = Mock()
            mock_query.filter.return_value.count.return_value = 1
            self.mock_session.query.return_value = mock_query
            
            # Call function
            result = await setup_status(self.mock_session)
            
            # Assertions
            assert result["debug_mode"] is True
            assert result["admin_users_count"] == 1
            assert result["has_admin"] is True
            assert result["database_connected"] is True
    
    @pytest.mark.asyncio
    async def test_setup_status_no_admin(self):
        """Test setup status when no admin exists"""
        with patch('app.api.routers.setup.settings') as mock_settings:
            # Setup mocks
            mock_settings.DEBUG = True
            
            # Mock session query
            mock_query = Mock()
            mock_query.filter.return_value.count.return_value = 0
            self.mock_session.query.return_value = mock_query
            
            # Call function
            result = await setup_status(self.mock_session)
            
            # Assertions
            assert result["debug_mode"] is True
            assert result["admin_users_count"] == 0
            assert result["has_admin"] is False
            assert result["database_connected"] is True
    
    @pytest.mark.asyncio
    async def test_setup_status_not_debug_mode(self):
        """Test setup status when not in debug mode"""
        with patch('app.api.routers.setup.settings') as mock_settings:
            # Setup mocks
            mock_settings.DEBUG = False
            
            with pytest.raises(HTTPException) as exc_info:
                await setup_status(self.mock_session)
            
            assert exc_info.value.status_code == 403
            assert "Setup endpoints only available in debug mode" in exc_info.value.detail
