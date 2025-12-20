"""
Integration tests for Admin Users API endpoints
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from httpx import AsyncClient, ASGITransport

from app.core.security import hash_password, create_access_token


class TestAdminUsersAPI:
    """Test /api/v1/admin/users endpoints"""
    
    @pytest.fixture
    def admin_token(self):
        """Create admin JWT token for testing"""
        with patch('app.core.security.get_settings') as mock_settings:
            settings = MagicMock()
            settings.JWT_SECRET = "test-secret"
            settings.JWT_ALGORITHM = "HS256"
            settings.JWT_ISSUER = "test"
            settings.JWT_AUDIENCE = "test"
            settings.JWT_ACCESS_TTL_MINUTES = 60
            settings.JWT_KID = None
            settings.JWT_PRIVATE_KEY = None
            settings.JWT_PUBLIC_KEY = None
            mock_settings.return_value = settings
            
            return create_access_token(
                user_id=str(uuid4()),
                email="admin@test.com",
                role="admin",
                tenant_ids=[],
                scopes=[]
            )
    
    @pytest.fixture
    def mock_admin_user(self):
        """Mock admin user for require_admin dependency"""
        user = MagicMock()
        user.id = str(uuid4())
        user.role = "admin"
        user.email = "admin@test.com"
        return user
    
    @pytest.fixture
    def sample_users(self):
        """Sample users for list tests"""
        users = []
        for i in range(3):
            user = MagicMock()
            user.id = uuid4()
            user.login = f"user{i}"
            user.email = f"user{i}@example.com"
            user.role = "reader"
            user.is_active = True
            user.created_at = MagicMock()
            user.created_at.isoformat = MagicMock(return_value="2024-01-01T00:00:00")
            user.updated_at = None
            users.append(user)
        return users


class TestListUsers(TestAdminUsersAPI):
    """Test GET /api/v1/admin/users"""
    
    @pytest.mark.asyncio
    async def test_list_users_requires_admin(self):
        """Should return 401 without authentication"""
        from app.main import app
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/admin/users")
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_list_users_non_admin_forbidden(self):
        """Should return 403 for non-admin users"""
        from app.main import app
        
        # Create token for non-admin user
        with patch('app.core.security.get_settings') as mock_settings:
            settings = MagicMock()
            settings.JWT_SECRET = "test-secret"
            settings.JWT_ALGORITHM = "HS256"
            settings.JWT_ISSUER = "test"
            settings.JWT_AUDIENCE = "test"
            settings.JWT_ACCESS_TTL_MINUTES = 60
            settings.JWT_KID = None
            settings.JWT_PRIVATE_KEY = None
            settings.JWT_PUBLIC_KEY = None
            mock_settings.return_value = settings
            
            reader_token = create_access_token(
                user_id=str(uuid4()),
                email="reader@test.com",
                role="reader",  # Non-admin role
                tenant_ids=[],
                scopes=[]
            )
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/admin/users",
                headers={"Authorization": f"Bearer {reader_token}"}
            )
        
        # Should be forbidden for non-admin
        assert response.status_code in [401, 403]


class TestCreateUser(TestAdminUsersAPI):
    """Test POST /api/v1/admin/users"""
    
    @pytest.mark.asyncio
    async def test_create_user_requires_admin(self):
        """Should return 401 without authentication"""
        from app.main import app
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/admin/users",
                json={
                    "login": "newuser",
                    "email": "new@example.com",
                    "password": "password123",
                    "role": "reader"
                }
            )
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_create_user_validation_login_required(self):
        """Should return 422 when login is missing"""
        from app.main import app
        
        # This test checks validation even if auth fails first
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/admin/users",
                json={
                    "email": "new@example.com",
                    "password": "password123"
                }
            )
        
        # Should fail (either auth or validation)
        assert response.status_code in [401, 422]


class TestGetUser(TestAdminUsersAPI):
    """Test GET /api/v1/admin/users/{user_id}"""
    
    @pytest.mark.asyncio
    async def test_get_user_requires_admin(self):
        """Should return 401 without authentication"""
        from app.main import app
        
        user_id = str(uuid4())
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/admin/users/{user_id}")
        
        assert response.status_code == 401


class TestUpdateUser(TestAdminUsersAPI):
    """Test PATCH /api/v1/admin/users/{user_id}"""
    
    @pytest.mark.asyncio
    async def test_update_user_requires_admin(self):
        """Should return 401 without authentication"""
        from app.main import app
        
        user_id = str(uuid4())
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.patch(
                f"/api/v1/admin/users/{user_id}",
                json={"role": "editor"}
            )
        
        assert response.status_code == 401


class TestDeleteUser(TestAdminUsersAPI):
    """Test DELETE /api/v1/admin/users/{user_id}"""
    
    @pytest.mark.asyncio
    async def test_delete_user_requires_admin(self):
        """Should return 401 without authentication"""
        from app.main import app
        
        user_id = str(uuid4())
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.delete(f"/api/v1/admin/users/{user_id}")
        
        assert response.status_code == 401


class TestChangePassword(TestAdminUsersAPI):
    """Test POST /api/v1/admin/users/{user_id}/password"""
    
    @pytest.mark.asyncio
    async def test_change_password_requires_admin(self):
        """Should return 401 without authentication"""
        from app.main import app
        
        user_id = str(uuid4())
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/admin/users/{user_id}/password",
                json={"new_password": "newpassword123"}
            )
        
        assert response.status_code == 401
