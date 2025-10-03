"""
Базовые unit тесты для проверки инфраструктуры тестирования.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.users_service import AsyncUsersService


@pytest.mark.unit
class TestBasicInfrastructure:
    """Тесты базовой инфраструктуры тестирования."""

    @pytest.mark.asyncio
    async def test_mock_db_session(self, mock_db_session):
        """Тест что mock_db_session работает корректно."""
        # Arrange
        mock_db_session.scalar.return_value = None
        
        # Act
        result = await mock_db_session.scalar("SELECT 1")
        
        # Assert
        assert result is None
        mock_db_session.scalar.assert_called_once_with("SELECT 1")

    @pytest.mark.asyncio
    async def test_mock_redis(self, mock_redis):
        """Тест что mock_redis работает корректно."""
        # Arrange
        mock_redis.get.return_value = "test_value"
        
        # Act
        result = await mock_redis.get("test_key")
        
        # Assert
        assert result == "test_value"
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_users_service_initialization(self, mock_db_session):
        """Тест инициализации UsersService."""
        # Arrange
        from app.repositories.users_repo import AsyncUsersRepository
        mock_repo = AsyncUsersRepository(mock_db_session)
        
        # Act
        service = AsyncUsersService(mock_repo)
        
        # Assert
        assert service.users_repo == mock_repo

    @pytest.mark.asyncio
    async def test_sample_user_data_fixture(self, sample_user_data):
        """Тест фикстуры sample_user_data."""
        # Assert
        assert sample_user_data["email"] == "test@example.com"
        assert sample_user_data["username"] == "testuser"
        assert sample_user_data["is_active"] is True

    @pytest.mark.asyncio
    async def test_sample_chat_data_fixture(self, sample_chat_data):
        """Тест фикстуры sample_chat_data."""
        # Assert
        assert sample_chat_data["title"] == "Test Chat"
        assert sample_chat_data["user_id"] == 1

    @pytest.mark.asyncio
    async def test_sample_message_data_fixture(self, sample_message_data):
        """Тест фикстуры sample_message_data."""
        # Assert
        assert sample_message_data["content"] == "Test message"
        assert sample_message_data["role"] == "user"
