"""
Unit тесты для моделей чатов.
"""
import pytest
from datetime import datetime
from app.models.chat import Chats, ChatMessages


class TestChatModel:
    """Unit тесты для модели Chats."""

    def test_chats_model_creation(self):
        """Тест создания модели Chats."""
        # Arrange
        import uuid
        chat_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "owner_id": uuid.uuid4(),
            "name": "Test Chat",
            "tags": ["test", "chat"],
            "version": 1
        }

        # Act
        chat = Chats(**chat_data)

        # Assert
        assert chat.id == chat_data["id"]
        assert chat.tenant_id == chat_data["tenant_id"]
        assert chat.owner_id == chat_data["owner_id"]
        assert chat.name == "Test Chat"
        assert chat.tags == ["test", "chat"]
        assert chat.version == 1

    def test_chat_messages_model_creation(self):
        """Тест создания модели ChatMessages."""
        # Arrange
        import uuid
        message_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "chat_id": uuid.uuid4(),
            "role": "user",
            "content": {"text": "Hello, how are you?"},
            "model": "gpt-3.5-turbo",
            "meta": {"model": "gpt-3.5-turbo"}
        }

        # Act
        message = ChatMessages(**message_data)

        # Assert
        assert message.id == message_data["id"]
        assert message.tenant_id == message_data["tenant_id"]
        assert message.chat_id == message_data["chat_id"]
        assert message.role == "user"
        assert message.content == {"text": "Hello, how are you?"}
        assert message.model == "gpt-3.5-turbo"
        assert message.meta == {"model": "gpt-3.5-turbo"}

    def test_chat_messages_with_optional_fields(self):
        """Тест создания модели ChatMessages с опциональными полями."""
        # Arrange
        import uuid
        message_data = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "chat_id": uuid.uuid4(),
            "role": "assistant",
            "content": {"text": "I'm doing well, thank you!"},
            "model": "gpt-3.5-turbo",
            "tokens_in": 10,
            "tokens_out": 8
        }

        # Act
        message = ChatMessages(**message_data)

        # Assert
        assert message.id == message_data["id"]
        assert message.tenant_id == message_data["tenant_id"]
        assert message.chat_id == message_data["chat_id"]
        assert message.role == "assistant"
        assert message.content == {"text": "I'm doing well, thank you!"}
        assert message.model == "gpt-3.5-turbo"
        assert message.tokens_in == 10
        assert message.tokens_out == 8
