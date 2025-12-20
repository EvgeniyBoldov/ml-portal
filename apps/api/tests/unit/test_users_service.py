"""
Unit tests for AsyncUsersService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.users_service import AsyncUsersService
from app.core.security import hash_password, verify_password


class TestAsyncUsersService:
    """Test AsyncUsersService methods"""
    
    @pytest.fixture
    def mock_users_repo(self):
        """Mock users repository"""
        repo = AsyncMock()
        repo.session = AsyncMock()
        repo.session.flush = AsyncMock()
        repo.session.refresh = AsyncMock()
        repo.session.delete = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_by_login = AsyncMock(return_value=None)
        repo.get_by_email = AsyncMock(return_value=None)
        repo.create = AsyncMock()
        repo.add_to_tenant = AsyncMock()
        return repo
    
    @pytest.fixture
    def users_service(self, mock_users_repo):
        """Create AsyncUsersService with mock repo"""
        return AsyncUsersService(mock_users_repo)
    
    @pytest.fixture
    def sample_user(self):
        """Create a sample user mock"""
        user = MagicMock()
        user.id = uuid4()
        user.login = "testuser"
        user.email = "test@example.com"
        user.role = "reader"
        user.is_active = True
        user.password_hash = hash_password("correct_password")
        user.created_at = MagicMock()
        user.updated_at = MagicMock()
        return user


class TestAuthentication(TestAsyncUsersService):
    """Test user authentication"""
    
    @pytest.mark.asyncio
    async def test_authenticate_user_by_login_success(self, users_service, mock_users_repo, sample_user):
        """Should authenticate user by login with correct password"""
        mock_users_repo.get_by_login.return_value = sample_user
        
        result = await users_service.authenticate_user("testuser", "correct_password")
        
        assert result is not None
        assert result.id == sample_user.id
        mock_users_repo.get_by_login.assert_called_once_with("testuser")
    
    @pytest.mark.asyncio
    async def test_authenticate_user_by_email_success(self, users_service, mock_users_repo, sample_user):
        """Should authenticate user by email with correct password"""
        mock_users_repo.get_by_login.return_value = None
        mock_users_repo.get_by_email.return_value = sample_user
        
        result = await users_service.authenticate_user("test@example.com", "correct_password")
        
        assert result is not None
        assert result.id == sample_user.id
        mock_users_repo.get_by_email.assert_called_once_with("test@example.com")
    
    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, users_service, mock_users_repo, sample_user):
        """Should return None for wrong password"""
        mock_users_repo.get_by_login.return_value = sample_user
        
        result = await users_service.authenticate_user("testuser", "wrong_password")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, users_service, mock_users_repo):
        """Should return None for non-existent user"""
        mock_users_repo.get_by_login.return_value = None
        mock_users_repo.get_by_email.return_value = None
        
        result = await users_service.authenticate_user("nonexistent", "password")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_authenticate_user_inactive(self, users_service, mock_users_repo, sample_user):
        """Should return None for inactive user"""
        sample_user.is_active = False
        mock_users_repo.get_by_login.return_value = sample_user
        
        result = await users_service.authenticate_user("testuser", "correct_password")
        
        assert result is None


class TestCreateUser(TestAsyncUsersService):
    """Test user creation"""
    
    @pytest.mark.asyncio
    async def test_create_user_success(self, users_service, mock_users_repo):
        """Should create user with hashed password"""
        created_user = MagicMock()
        created_user.id = uuid4()
        created_user.login = "newuser"
        created_user.email = "new@example.com"
        created_user.role = "reader"
        mock_users_repo.create.return_value = created_user
        
        result = await users_service.create_user(
            login="newuser",
            email="new@example.com",
            password="secure_password_123",
            role="reader"
        )
        
        assert result is not None
        assert result.login == "newuser"
        
        # Verify create was called with hashed password
        mock_users_repo.create.assert_called_once()
        call_kwargs = mock_users_repo.create.call_args.kwargs
        assert call_kwargs["login"] == "newuser"
        assert call_kwargs["email"] == "new@example.com"
        assert call_kwargs["role"] == "reader"
        assert call_kwargs["is_active"] is True
        # Password should be hashed, not plaintext
        assert call_kwargs["password_hash"] != "secure_password_123"
        assert len(call_kwargs["password_hash"]) > 20  # Argon2 hash is long
    
    @pytest.mark.asyncio
    async def test_create_user_password_is_verifiable(self, users_service, mock_users_repo):
        """Created user's password should be verifiable with argon2"""
        created_user = MagicMock()
        created_user.id = uuid4()
        mock_users_repo.create.return_value = created_user
        
        password = "my_secure_password"
        await users_service.create_user(
            login="verifyuser",
            email="verify@example.com",
            password=password,
            role="reader"
        )
        
        # Get the hash that was passed to create
        call_kwargs = mock_users_repo.create.call_args.kwargs
        stored_hash = call_kwargs["password_hash"]
        
        # Verify the password can be verified with argon2
        assert verify_password(password, stored_hash) is True
        assert verify_password("wrong_password", stored_hash) is False
    
    @pytest.mark.asyncio
    async def test_create_user_duplicate_login(self, users_service, mock_users_repo, sample_user):
        """Should raise ValueError for duplicate login"""
        mock_users_repo.get_by_login.return_value = sample_user
        
        with pytest.raises(ValueError) as exc_info:
            await users_service.create_user(
                login="testuser",
                email="different@example.com",
                password="password",
                role="reader"
            )
        
        assert "login already exists" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, users_service, mock_users_repo, sample_user):
        """Should raise ValueError for duplicate email"""
        mock_users_repo.get_by_login.return_value = None
        mock_users_repo.get_by_email.return_value = sample_user
        
        with pytest.raises(ValueError) as exc_info:
            await users_service.create_user(
                login="differentuser",
                email="test@example.com",
                password="password",
                role="reader"
            )
        
        assert "email already exists" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_create_user_with_tenants(self, users_service, mock_users_repo):
        """Should add user to specified tenants"""
        created_user = MagicMock()
        created_user.id = uuid4()
        mock_users_repo.create.return_value = created_user
        
        tenant_ids = [str(uuid4()), str(uuid4())]
        
        await users_service.create_user(
            login="tenantuser",
            email="tenant@example.com",
            password="password",
            role="reader",
            tenant_ids=tenant_ids
        )
        
        # Should call add_to_tenant for each tenant
        assert mock_users_repo.add_to_tenant.call_count == 2
        
        # First tenant should be default
        first_call = mock_users_repo.add_to_tenant.call_args_list[0]
        assert first_call.kwargs.get("is_default") is True or first_call.args[-1] is True


class TestUpdateUser(TestAsyncUsersService):
    """Test user update"""
    
    @pytest.mark.asyncio
    async def test_update_user_email(self, users_service, mock_users_repo, sample_user):
        """Should update user email"""
        mock_users_repo.get_by_id.return_value = sample_user
        mock_users_repo.get_by_email.return_value = None
        
        result = await users_service.update_user(
            str(sample_user.id),
            {"email": "updated@example.com"}
        )
        
        assert sample_user.email == "updated@example.com"
    
    @pytest.mark.asyncio
    async def test_update_user_role(self, users_service, mock_users_repo, sample_user):
        """Should update user role"""
        mock_users_repo.get_by_id.return_value = sample_user
        
        await users_service.update_user(
            str(sample_user.id),
            {"role": "admin"}
        )
        
        assert sample_user.role == "admin"
    
    @pytest.mark.asyncio
    async def test_update_user_password(self, users_service, mock_users_repo, sample_user):
        """Should update user password with argon2 hash"""
        mock_users_repo.get_by_id.return_value = sample_user
        old_hash = sample_user.password_hash
        
        await users_service.update_user(
            str(sample_user.id),
            {"password": "new_secure_password"}
        )
        
        # Password hash should be updated
        assert sample_user.password_hash != old_hash
        # New password should be verifiable
        assert verify_password("new_secure_password", sample_user.password_hash) is True
    
    @pytest.mark.asyncio
    async def test_update_user_deactivate(self, users_service, mock_users_repo, sample_user):
        """Should deactivate user"""
        mock_users_repo.get_by_id.return_value = sample_user
        
        await users_service.update_user(
            str(sample_user.id),
            {"is_active": False}
        )
        
        assert sample_user.is_active is False
    
    @pytest.mark.asyncio
    async def test_update_user_not_found(self, users_service, mock_users_repo):
        """Should raise ValueError for non-existent user"""
        mock_users_repo.get_by_id.return_value = None
        
        with pytest.raises(ValueError) as exc_info:
            await users_service.update_user(
                str(uuid4()),
                {"email": "new@example.com"}
            )
        
        assert "not found" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_update_user_email_taken(self, users_service, mock_users_repo, sample_user):
        """Should raise ValueError if email is taken by another user"""
        other_user = MagicMock()
        other_user.id = uuid4()  # Different ID
        
        mock_users_repo.get_by_id.return_value = sample_user
        mock_users_repo.get_by_email.return_value = other_user
        
        with pytest.raises(ValueError) as exc_info:
            await users_service.update_user(
                str(sample_user.id),
                {"email": "taken@example.com"}
            )
        
        assert "taken" in str(exc_info.value).lower()


class TestDeleteUser(TestAsyncUsersService):
    """Test user deletion"""
    
    @pytest.mark.asyncio
    async def test_delete_user_success(self, users_service, mock_users_repo, sample_user):
        """Should delete existing user"""
        mock_users_repo.get_by_id.return_value = sample_user
        
        await users_service.delete_user(str(sample_user.id))
        
        mock_users_repo.session.delete.assert_called_once_with(sample_user)
        mock_users_repo.session.flush.assert_called()
    
    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, users_service, mock_users_repo):
        """Should raise ValueError for non-existent user"""
        mock_users_repo.get_by_id.return_value = None
        
        with pytest.raises(ValueError) as exc_info:
            await users_service.delete_user(str(uuid4()))
        
        assert "not found" in str(exc_info.value).lower()


class TestGetUserById(TestAsyncUsersService):
    """Test get user by ID"""
    
    @pytest.mark.asyncio
    async def test_get_user_by_id_found(self, users_service, mock_users_repo, sample_user):
        """Should return user when found"""
        mock_users_repo.get_by_id.return_value = sample_user
        
        result = await users_service.get_user_by_id(str(sample_user.id))
        
        assert result is not None
        assert result.id == sample_user.id
    
    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, users_service, mock_users_repo):
        """Should return None when user not found"""
        mock_users_repo.get_by_id.return_value = None
        
        result = await users_service.get_user_by_id(str(uuid4()))
        
        assert result is None


class TestPasswordHashingIntegration:
    """Integration tests for password hashing in user service"""
    
    @pytest.mark.asyncio
    async def test_create_and_authenticate_user(self):
        """Full flow: create user, then authenticate"""
        # This test verifies that the same hashing algorithm is used
        # for both creation and authentication
        
        mock_repo = AsyncMock()
        mock_repo.session = AsyncMock()
        mock_repo.session.flush = AsyncMock()
        mock_repo.get_by_login = AsyncMock(return_value=None)
        mock_repo.get_by_email = AsyncMock(return_value=None)
        
        # Capture the created user
        created_user = None
        async def capture_create(**kwargs):
            nonlocal created_user
            user = MagicMock()
            user.id = kwargs.get("id")
            user.login = kwargs.get("login")
            user.email = kwargs.get("email")
            user.password_hash = kwargs.get("password_hash")
            user.role = kwargs.get("role")
            user.is_active = kwargs.get("is_active", True)
            created_user = user
            return user
        
        mock_repo.create = capture_create
        
        service = AsyncUsersService(mock_repo)
        
        # Create user
        password = "test_password_for_flow"
        await service.create_user(
            login="flowuser",
            email="flow@example.com",
            password=password,
            role="reader"
        )
        
        assert created_user is not None
        
        # Now authenticate with the same password
        mock_repo.get_by_login.return_value = created_user
        
        auth_result = await service.authenticate_user("flowuser", password)
        
        assert auth_result is not None
        assert auth_result.login == "flowuser"
        
        # Wrong password should fail
        mock_repo.get_by_login.return_value = created_user
        wrong_result = await service.authenticate_user("flowuser", "wrong_password")
        
        assert wrong_result is None
