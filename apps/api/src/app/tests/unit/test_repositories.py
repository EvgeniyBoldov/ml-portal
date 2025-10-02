"""
Unit тесты для репозиториев.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.repositories.users_repo import UsersRepository
from app.repositories.chats_repo import ChatsRepository


class TestUsersRepository:
    """Unit тесты для UsersRepository."""

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
    def users_repo(self, mock_session):
        """Создает экземпляр UsersRepository с моками."""
        import uuid
        return UsersRepository(mock_session, uuid.uuid4())

    def test_get_by_id_success(self, users_repo, mock_session):
        """Тест успешного получения пользователя по ID."""
        # Arrange
        import uuid
        tenant_id = uuid.uuid4()
        user_id = "test-user-id"
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_user

        # Act
        result = users_repo.get_by_id(tenant_id, user_id)

        # Assert
        assert result is not None
        assert result.id == user_id
        mock_session.execute.assert_called_once()

    def test_get_by_login(self, users_repo, mock_session):
        """Тест получения пользователя по логину."""
        # Arrange
        login = "testuser"
        mock_user = MagicMock()
        mock_user.login = login
        
        # Мокаем метод get_by_field, который используется в get_by_login
        users_repo.get_by_field = MagicMock(return_value=mock_user)

        # Act
        result = users_repo.get_by_login(login)

        # Assert
        assert result is not None
        assert result.login == login
        users_repo.get_by_field.assert_called_once_with('login', login)

    def test_add_user(self, users_repo, mock_session):
        """Тест добавления пользователя."""
        # Arrange
        mock_user = MagicMock()

        # Act
        users_repo.add(mock_user)

        # Assert
        mock_session.add.assert_called_once_with(mock_user)

    def test_commit(self, users_repo, mock_session):
        """Тест коммита изменений."""
        # Act
        users_repo.commit()

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
