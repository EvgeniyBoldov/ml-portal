"""
Unit тесты для репозиториев.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.repositories.users_repo import AsyncUsersRepository
from app.repositories.chats_repo import ChatsRepository


class TestAsyncUsersRepository:
    """Unit тесты для AsyncUsersRepository."""

    @pytest.fixture
    def mock_session(self):
        """Создает мок сессии."""
        session = MagicMock()
        session.execute = MagicMock()
        session.add = MagicMock()
        session.commit = MagicMock()
        session.refresh = AsyncMock()
        session.rollback = MagicMock()
        session.flush = AsyncMock()
        session.get = AsyncMock()
        return session

    @pytest.fixture
    def users_repo(self, mock_session):
        """Создает экземпляр AsyncUsersRepository с моками."""
        return AsyncUsersRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, users_repo, mock_session):
        """Тест успешного получения пользователя по ID."""
        # Arrange
        import uuid
        user_id = "test-user-id"
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_session.get.return_value = mock_user

        # Act
        result = await users_repo.get_by_id(user_id)

        # Assert
        assert result is not None
        assert result.id == user_id
        mock_session.get.assert_called_once_with(users_repo.model, user_id)

    def test_get_by_login(self, users_repo, mock_session):
        """Тест получения пользователя по логину."""
        # Arrange
        login = "testuser"
        mock_user = MagicMock()
        mock_user.login = login
        
        # Мокаем метод list, который используется для поиска по полю
        users_repo.list = MagicMock(return_value=[mock_user])

        # Act
        result = users_repo.list(filters={'login': login})

        # Assert
        assert result is not None
        assert len(result) == 1
        assert result[0].login == login
        users_repo.list.assert_called_once_with(filters={'login': login})

    @pytest.mark.asyncio
    async def test_add_user(self, users_repo, mock_session):
        """Тест создания пользователя."""
        # Arrange
        user_data = {
            "login": "testuser",
            "email": "test@example.com",
            "password_hash": "hashed_password",
            "is_active": True,
            "role": "reader"
        }

        # Act
        result = await users_repo.create(**user_data)

        # Assert
        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    def test_commit(self, users_repo, mock_session):
        """Тест коммита изменений."""
        # Act
        mock_session.commit()

        # Assert
        mock_session.commit.assert_called_once()


class TestChatsRepository:
    """Unit тесты для ChatsRepository."""

    @pytest.fixture
    def mock_session(self):
        """Создает мок сессии."""
        session = MagicMock()
        session.execute = MagicMock()
        session.add = MagicMock()
        session.commit = MagicMock()
        session.refresh = MagicMock()
        session.rollback = MagicMock()
        session.flush = MagicMock()
        return session

    @pytest.fixture
    def chats_repo(self, mock_session):
        """Создает экземпляр ChatsRepository с моками."""
        import uuid
        return ChatsRepository(mock_session, uuid.uuid4())

    def test_get_by_id_success(self, chats_repo, mock_session):
        """Тест успешного получения чата по ID."""
        # Arrange
        import uuid
        tenant_id = uuid.uuid4()
        chat_id = "test-chat-id"
        mock_chat = MagicMock()
        mock_chat.id = chat_id
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_chat

        # Act
        result = chats_repo.get_by_id(tenant_id, chat_id)

        # Assert
        assert result is not None
        assert result.id == chat_id
        mock_session.execute.assert_called_once()

    def test_create_chat(self, chats_repo, mock_session):
        """Тест создания чата."""
        # Arrange
        import uuid
        tenant_id = uuid.uuid4()
        owner_id = "test-owner"
        name = "Test Chat"
        tags = ["test", "chat"]
        
        # Мокаем метод create
        chats_repo.create = MagicMock(return_value=MagicMock())

        # Act
        result = chats_repo.create_chat(owner_id, name, tags)

        # Assert
        assert result is not None
        chats_repo.create.assert_called_once()

    def test_get_user_chats(self, chats_repo, mock_session):
        """Тест получения чатов пользователя."""
        # Arrange
        user_id = "test-user"
        mock_chats = [MagicMock(), MagicMock()]
        chats_repo.list = MagicMock(return_value=mock_chats)

        # Act
        result = chats_repo.get_user_chats(user_id)

        # Assert
        assert result is not None
        assert len(result) == 2
        chats_repo.list.assert_called_once()
