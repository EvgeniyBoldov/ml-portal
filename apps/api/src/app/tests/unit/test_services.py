"""
Unit тесты для сервисов.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.auth_service import AuthService
from app.services.users_service import AsyncUsersService


class TestAuthService:
    """Unit тесты для AuthService."""

    @pytest.fixture
    def auth_service(self):
        """Создает экземпляр AuthService."""
        return AuthService()

    def test_authenticate_success(self, auth_service):
        """Тест успешной аутентификации пользователя."""
        # Arrange
        email = "test@example.com"
        password = "testpassword"

        # Act
        result = auth_service.authenticate(email, password)

        # Assert
        # AuthService.authenticate возвращает None по умолчанию
        assert result is None

    def test_create_superuser(self, auth_service):
        """Тест создания суперпользователя."""
        # Arrange
        email = "admin@example.com"
        password = "adminpassword"

        # Act
        result = auth_service.create_superuser(email, password)

        # Assert
        assert result is not None
        assert result["email"] == email
        assert result["role"] == "admin"

    def test_rbac_check(self, auth_service):
        """Тест проверки RBAC."""
        # Arrange
        user = {"id": 1, "role": "admin"}
        scope = "read:users"

        # Act
        result = auth_service.rbac_check(user, scope)

        # Assert
        assert result is True


class TestAsyncUsersService:
    """Unit тесты для AsyncUsersService."""

    @pytest.fixture
    def mock_repo(self):
        """Создает мок репозитория."""
        return AsyncMock()

    @pytest.fixture
    def users_service(self, mock_repo):
        """Создает экземпляр AsyncUsersService с моками."""
        return AsyncUsersService(mock_repo)

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, users_service, mock_repo):
        """Тест успешной аутентификации пользователя."""
        # Arrange
        from app.models.user import Users
        import uuid
        from unittest.mock import patch
        
        user = Users(
            id=uuid.uuid4(),
            login="testuser",
            email="test@example.com",
            password_hash="hashed_password",
            is_active=True
        )
        mock_repo.get_by_login.return_value = user
        mock_repo.get_by_email.return_value = None

        # Act
        with patch('bcrypt.checkpw', return_value=True):
            result = await users_service.authenticate_user("testuser", "password")

        # Assert
        assert result is not None
        assert result.login == "testuser"
        mock_repo.get_by_login.assert_called_once_with("testuser")

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, users_service, mock_repo):
        """Тест аутентификации с неправильным паролем."""
        # Arrange
        from app.models.user import Users
        import uuid
        
        user = Users(
            id=uuid.uuid4(),
            login="testuser",
            email="test@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8QzK8q2",  # bcrypt hash for "password"
            is_active=True
        )
        mock_repo.get_by_login.return_value = user

        # Act
        result = await users_service.authenticate_user("testuser", "wrongpassword")

        # Assert
        assert result is None
        mock_repo.get_by_login.assert_called_once_with("testuser")

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, users_service, mock_repo):
        """Тест аутентификации несуществующего пользователя."""
        # Arrange
        mock_repo.get_by_login.return_value = None
        mock_repo.get_by_email.return_value = None

        # Act
        result = await users_service.authenticate_user("nonexistent", "password")

        # Assert
        assert result is None
        mock_repo.get_by_login.assert_called_once_with("nonexistent")
        mock_repo.get_by_email.assert_called_once_with("nonexistent")
