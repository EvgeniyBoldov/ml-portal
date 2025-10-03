"""
Unit тесты для Pydantic схем.
Тестирует валидацию данных и сериализацию.
"""
import pytest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError

from app.schemas.users import UserBase, UserCreate, UserUpdate, UserResponse, UserRole
from app.schemas.repository_schemas import ChatCreateRequest, ChatMessageCreateRequest, PaginatedResponse
from app.schemas.rag import RAGUploadRequest, RAGSearchRequest
from app.schemas.common import ProblemDetails


@pytest.mark.unit
class TestUserSchemas:
    """Тесты для схем пользователей."""

    def test_user_base_valid_data(self):
        """Тест базовой схемы пользователя с валидными данными."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "role": "reader"
        }

        # Act
        user = UserBase(**user_data)

        # Assert
        assert user.email == "test@example.com"
        assert user.role == UserRole.READER
        assert user.is_active is True  # Default value

    def test_user_base_invalid_email(self):
        """Тест базовой схемы пользователя с невалидным email."""
        # Arrange
        user_data = {
            "email": "invalid-email",
            "role": "reader"
        }

        # Act
        user = UserBase(**user_data)

        # Assert - Pydantic не валидирует email по умолчанию
        assert user.email == "invalid-email"
        assert user.role == UserRole.READER

    def test_user_base_invalid_role(self):
        """Тест базовой схемы пользователя с невалидной ролью."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "role": "invalid_role"
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            UserBase(**user_data)

    def test_user_create_with_password(self):
        """Тест создания пользователя с паролем."""
        # Arrange
        user_data = {
            "email": "test@example.com",
            "password": "securepassword123",
            "role": "editor"
        }

        # Act
        user = UserCreate(**user_data)

        # Assert
        assert user.email == "test@example.com"
        assert user.password == "securepassword123"
        assert user.role == UserRole.EDITOR

    def test_user_update_partial_data(self):
        """Тест обновления пользователя с частичными данными."""
        # Arrange
        update_data = {
            "email": "newemail@example.com",
            "role": "editor"
        }

        # Act
        user_update = UserUpdate(**update_data)

        # Assert
        assert user_update.email == "newemail@example.com"
        assert user_update.role == UserRole.EDITOR
        assert user_update.is_active is None  # Not provided

    def test_user_response_serialization(self):
        """Тест сериализации ответа пользователя."""
        # Arrange
        user_data = {
            "id": str(uuid.uuid4()),
            "email": "test@example.com",
            "role": "reader",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Act
        user_response = UserResponse(**user_data)

        # Assert
        assert user_response.email == "test@example.com"
        assert user_response.role == UserRole.READER
        assert user_response.is_active is True
        assert str(user_response.id) == user_data["id"]


@pytest.mark.unit
class TestChatSchemas:
    """Тесты для схем чатов."""

    def test_chat_create_request_valid_data(self):
        """Тест создания чата с валидными данными."""
        # Arrange
        chat_data = {
            "name": "Test Chat",
            "tags": ["test", "chat"]
        }

        # Act
        chat = ChatCreateRequest(**chat_data)

        # Assert
        assert chat.name == "Test Chat"
        assert chat.tags == ["test", "chat"]

    def test_chat_create_request_minimal_data(self):
        """Тест создания чата с минимальными данными."""
        # Arrange
        chat_data = {
            "name": "Minimal Chat"
        }

        # Act
        chat = ChatCreateRequest(**chat_data)

        # Assert
        assert chat.name == "Minimal Chat"
        assert chat.tags is None

    def test_chat_message_create_request_valid_data(self):
        """Тест создания сообщения с валидными данными."""
        # Arrange
        message_data = {
            "role": "user",
            "content": {"text": "Hello, world!"}
        }

        # Act
        message = ChatMessageCreateRequest(**message_data)

        # Assert
        assert message.role == "user"
        assert message.content == {"text": "Hello, world!"}

    def test_chat_message_create_request_string_content(self):
        """Тест создания сообщения со строковым контентом."""
        # Arrange
        message_data = {
            "role": "user",
            "content": "Hello, world!"
        }

        # Act
        message = ChatMessageCreateRequest(**message_data)

        # Assert
        assert message.role == "user"
        assert message.content == {"text": "Hello, world!"}

    def test_chat_message_create_request_invalid_role(self):
        """Тест создания сообщения с невалидной ролью."""
        # Arrange
        message_data = {
            "role": "invalid_role",
            "content": "Hello, world!"
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            ChatMessageCreateRequest(**message_data)


@pytest.mark.unit
class TestRAGSchemas:
    """Тесты для RAG схем."""

    def test_rag_upload_request_valid_data(self):
        """Тест загрузки RAG документа с валидными данными."""
        # Arrange
        upload_data = {
            "name": "test.pdf",
            "mime": "application/pdf",
            "size": 1024,
            "tags": ["test", "document"]
        }

        # Act
        upload_request = RAGUploadRequest(**upload_data)

        # Assert
        assert upload_request.name == "test.pdf"
        assert upload_request.mime == "application/pdf"
        assert upload_request.size == 1024
        assert upload_request.tags == ["test", "document"]

    def test_rag_search_request_valid_data(self):
        """Тест поиска RAG с валидными данными."""
        # Arrange
        search_data = {
            "query": "test query",
            "limit": 20,
            "offset": 0
        }

        # Act
        search_request = RAGSearchRequest(**search_data)

        # Assert
        assert search_request.query == "test query"
        assert search_request.limit == 20
        assert search_request.offset == 0

    def test_rag_search_request_default_values(self):
        """Тест поиска RAG со значениями по умолчанию."""
        # Arrange
        search_data = {
            "query": "test query"
        }

        # Act
        search_request = RAGSearchRequest(**search_data)

        # Assert
        assert search_request.query == "test query"
        assert search_request.limit == 10  # Default value
        assert search_request.offset == 0  # Default value


@pytest.mark.unit
class TestCommonSchemas:
    """Тесты для общих схем."""

    def test_problem_details_serialization(self):
        """Тест сериализации деталей проблемы."""
        # Arrange
        problem_data = {
            "type": "validation_error",
            "title": "Validation Error",
            "status": 400,
            "detail": "Invalid input data"
        }

        # Act
        problem = ProblemDetails(**problem_data)

        # Assert
        assert problem.type == "validation_error"
        assert problem.title == "Validation Error"
        assert problem.status == 400
        assert problem.detail == "Invalid input data"

    def test_paginated_response_serialization(self):
        """Тест сериализации ответа пагинации."""
        # Arrange
        pagination_data = {
            "items": [{"id": 1, "name": "test"}],
            "next_cursor": None,
            "total": 1,
            "has_more": False
        }

        # Act
        pagination = PaginatedResponse(**pagination_data)

        # Assert
        assert len(pagination.items) == 1
        assert pagination.next_cursor is None
        assert pagination.total == 1
        assert pagination.has_more is False