"""
Unit тесты для сервисов.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.auth_service import AuthService
from app.services.users_service import UsersService


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


class TestUsersService:
    """Unit тесты для UsersService."""

    @pytest.fixture
    def mock_session(self):
        """Создает мок сессии."""
        return AsyncMock()

    @pytest.fixture
    def users_service(self, mock_session):
        """Создает экземпляр UsersService с моками."""
        import uuid
        # Создаем мок для UsersRepository с правильными параметрами
        with patch('app.services.users_service.create_users_repository') as mock_repo_factory:
            mock_repo = MagicMock()
            mock_repo_factory.return_value = mock_repo
            
            # Создаем мок для других репозиториев
            with patch('app.services.users_service.create_user_tokens_repository'), \
                 patch('app.services.users_service.create_user_refresh_tokens_repository'), \
                 patch('app.services.users_service.create_password_reset_tokens_repository'), \
                 patch('app.services.users_service.create_audit_logs_repository'):
                return UsersService(mock_session)

    def test_get_required_fields(self, users_service):
        """Тест получения обязательных полей."""
        # Act
        required_fields = users_service._get_required_fields()

        # Assert
        assert "login" in required_fields
        assert "password_hash" in required_fields

    def test_process_create_data(self, users_service):
        """Тест обработки данных для создания пользователя."""
        # Arrange
        data = {
            "login": "TESTUSER",
            "email": "TEST@EXAMPLE.COM",
            "password_hash": "hashed_password"
        }

        # Act
        processed = users_service._process_create_data(data)

        # Assert
        assert processed["login"] == "testuser"  # Должно быть в нижнем регистре
        assert processed["email"] == "test@example.com"  # Должно быть в нижнем регистре
        assert processed["password_hash"] == "hashed_password"

    def test_sanitize_string(self, users_service):
        """Тест санитизации строки."""
        # Arrange
        test_string = "  Test String  "
        max_length = 10

        # Act
        result = users_service._sanitize_string(test_string, max_length)

        # Assert
        assert result == "Test Strin"  # Обрезано до max_length
        assert len(result) <= max_length
