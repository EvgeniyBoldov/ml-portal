"""
Simple unit tests for chats router
"""
import pytest
from unittest.mock import Mock

from app.api.routers.chats import _ser_chat, _ser_msg
from app.models.chat import Chats, ChatMessages


class TestChatsRouterSimple:
    """Test chats router functions - simple version"""
    
    def setup_method(self):
        """Setup test method"""
        # Mock chat
        self.mock_chat = Mock(spec=Chats)
        self.mock_chat.id = "chat123"
        self.mock_chat.name = "Test Chat"
        self.mock_chat.owner_id = "user123"
        self.mock_chat.tags = ["tag1", "tag2"]
        self.mock_chat.created_at = Mock()
        self.mock_chat.created_at.isoformat.return_value = "2023-01-01T00:00:00"
        self.mock_chat.updated_at = Mock()
        self.mock_chat.updated_at.isoformat.return_value = "2023-01-01T00:00:00"
        self.mock_chat.last_message_at = None
        
        # Mock chat message
        self.mock_message = Mock(spec=ChatMessages)
        self.mock_message.id = "msg123"
        self.mock_message.chat_id = "chat123"
        self.mock_message.role = "user"
        self.mock_message.content = "Hello"
        self.mock_message.created_at = Mock()
        self.mock_message.created_at.isoformat.return_value = "2023-01-01T00:00:00"
    
    def test_ser_chat(self):
        """Test _ser_chat function"""
        result = _ser_chat(self.mock_chat)
        
        assert result["id"] == "chat123"
        assert result["name"] == "Test Chat"
        assert result["tags"] == ["tag1", "tag2"]
        assert result["created_at"] == "2023-01-01T00:00:00"
        assert result["updated_at"] == "2023-01-01T00:00:00"
        assert result["last_message_at"] is None
    
    def test_ser_msg(self):
        """Test _ser_msg function"""
        result = _ser_msg(self.mock_message)
        
        assert result["id"] == "msg123"
        assert result["chat_id"] == "chat123"
        assert result["role"] == "user"
        assert result["content"] == "Hello"
