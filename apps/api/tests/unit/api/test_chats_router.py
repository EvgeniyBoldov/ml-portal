"""
Unit tests for chats router
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException, status

from app.api.routers.chats import (
    create_chat, list_chats, rename_chat, update_tags,
    post_message, list_messages, delete_chat
)
from app.models.chat import Chats, ChatMessages


class TestChatsRouter:
    """Test chats router functions"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        # Mock user as a dictionary (as expected by the router)
        self.mock_user = {"id": "user123", "role": "reader"}
        
        # Mock chat
        from datetime import datetime
        self.mock_chat = Mock(spec=Chats)
        self.mock_chat.id = "chat123"
        self.mock_chat.name = "Test Chat"
        self.mock_chat.tags = ["tag1", "tag2"]
        self.mock_chat.owner_id = "user123"  # Add owner_id
        self.mock_chat.created_at = datetime(2023, 1, 1, 0, 0, 0)
        self.mock_chat.updated_at = datetime(2023, 1, 1, 0, 0, 0)
        self.mock_chat.last_message_at = None
        
        # Mock chat message
        self.mock_message = Mock(spec=ChatMessages)
        self.mock_message.id = "msg123"
        self.mock_message.chat_id = "chat123"
        self.mock_message.role = "user"
        self.mock_message.content = "Hello"
        self.mock_message.created_at = "2023-01-01T00:00:00"
    
    def test_create_chat_success(self):
        """Test successful chat creation"""
        from app.api.schemas.chats import ChatCreateRequest
        
        chat_data = ChatCreateRequest(
            name="New Chat",
            tags=["tag1", "tag2"]
        )
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.create_chat.return_value = self.mock_chat
            
            # Call function
            result = create_chat(chat_data, self.mock_session, self.mock_user)
            
            # Assertions
            assert result["chat_id"] == "chat123"
            
            # Verify calls
            mock_repo.create_chat.assert_called_once_with(
                "user123", "New Chat", ["tag1", "tag2"]
            )
    
    def test_create_chat_without_name(self):
        """Test chat creation without name"""
        from app.api.schemas.chats import ChatCreateRequest
        
        chat_data = ChatCreateRequest(
            name=None,  # No name provided
            tags=["tag1", "tag2"]
        )
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.create_chat.return_value = self.mock_chat
            
            # Call function
            result = create_chat(chat_data, self.mock_session, self.mock_user)
            
            # Assertions
            assert result["chat_id"] == "chat123"
            
            # Verify calls
            mock_repo.create_chat.assert_called_once_with(
                "user123", None, ["tag1", "tag2"]
            )
    
    def test_create_chat_invalid_tags(self):
        """Test chat creation with invalid tags"""
        # This test should fail at the Pydantic validation level
        with pytest.raises(Exception):  # Pydantic validation error
            from app.api.schemas.chats import ChatCreateRequest
            ChatCreateRequest(
                name="New Chat",
                tags="invalid_tags"  # Should be a list, not string
            )
    
    def test_list_chats_success(self):
        """Test successful chats listing"""
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.list_chats.return_value = [self.mock_chat]
            
            # Call function
            result = list_chats(
                limit=10, cursor=None, q="", 
                session=self.mock_session, user=self.mock_user
            )
            
            # Assertions
            assert "items" in result
            assert "next_cursor" in result
            assert len(result["items"]) == 1
            assert result["items"][0]["id"] == "chat123"
            
            # Verify calls
            mock_repo.list_chats.assert_called_once_with("user123", q="", limit=10)
    
    def test_rename_chat_success(self):
        """Test successful chat rename"""
        from app.api.schemas.chats import ChatUpdateRequest
        
        rename_data = ChatUpdateRequest(name="Renamed Chat")
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_chat
            mock_repo.rename_chat.return_value = None
            mock_repo.get.return_value = self.mock_chat  # For the second call
            
            # Call function
            result = rename_chat("chat123", rename_data, self.mock_session, self.mock_user)
            
            # Assertions
            assert result["id"] == "chat123"
            assert result["name"] == "Test Chat"
            
            # Verify calls
            mock_repo.get.assert_called_with("chat123")
            mock_repo.rename_chat.assert_called_once_with("chat123", "Renamed Chat")
    
    def test_rename_chat_not_found(self):
        """Test rename chat with non-existent ID"""
        from app.api.schemas.chats import ChatUpdateRequest
        
        rename_data = ChatUpdateRequest(name="Renamed Chat")
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                rename_chat("nonexistent", rename_data, self.mock_session, self.mock_user)
            
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "not_found"
    
    def test_update_tags_success(self):
        """Test successful chat tags update"""
        from app.api.schemas.chats import ChatTagsUpdateRequest
        
        tags_data = ChatTagsUpdateRequest(tags=["newtag1", "newtag2"])
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_chat
            mock_repo.update_chat_tags.return_value = None
            
            # Call function
            result = update_tags(
                "chat123", tags_data, self.mock_session, self.mock_user
            )
            
            # Assertions
            assert result["id"] == "chat123"
            assert result["tags"] == ["newtag1", "newtag2"]
            
            # Verify calls
            mock_repo.get.assert_called_once_with("chat123")
            mock_repo.update_chat_tags.assert_called_once_with("chat123", ["newtag1", "newtag2"])
    
    def test_update_tags_not_found(self):
        """Test update chat tags with non-existent ID"""
        from app.api.schemas.chats import ChatTagsUpdateRequest
        
        tags_data = ChatTagsUpdateRequest(tags=["newtag1", "newtag2"])
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                update_tags(
                    "nonexistent", tags_data, self.mock_session, self.mock_user
                )
            
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "not_found"
    
    @pytest.mark.asyncio
    async def test_post_message_success(self):
        """Test successful message sending"""
        from app.api.schemas.chats import ChatMessageCreateRequest
        
        message_data = ChatMessageCreateRequest(
            content={"text": "Hello, how are you?"},
            role="user",
            response_stream=False,
            use_rag=False
        )
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class, \
             patch('app.api.routers.chats.llm_chat') as mock_llm_chat:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_chat
            mock_repo.add_message.return_value = self.mock_message
            mock_llm_chat.return_value = "Hello! I'm doing well, thank you!"
            
            # Call function
            result = await post_message(
                "chat123", message_data, self.mock_session, self.mock_user
            )
            
            # Assertions - post_message returns ChatMessageResponse
            assert result.id == "msg123"
            assert result.chat_id == "chat123"
            assert result.role == "user"
            assert result.content == {"text": "Hello, how are you?"}
            
            # Verify calls
            mock_repo.get.assert_called_once_with("chat123")
            mock_repo.add_message.assert_called()
    
    @pytest.mark.asyncio
    async def test_post_message_chat_not_found(self):
        """Test send message with non-existent chat ID"""
        from app.api.schemas.chats import ChatMessageCreateRequest
        
        message_data = ChatMessageCreateRequest(
            content={"text": "Hello, how are you?"},
            role="user",
            response_stream=False,
            use_rag=False
        )
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                await post_message(
                    "nonexistent", message_data, self.mock_session, self.mock_user
                )
            
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "not_found"
    
    @pytest.mark.asyncio
    async def test_post_message_stream_success(self):
        """Test successful streaming message sending"""
        message_data = {
            "content": "Hello, how are you?",
            "role": "user"
        }
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class, \
             patch('app.api.routers.chats.llm_chat') as mock_llm_chat:
            
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_chat
            mock_repo.add_message.return_value = self.mock_message
            mock_llm_chat.return_value = "Hello! I'm doing well, thank you!"
            
            # Call function - use post_message with streaming enabled
            from app.api.schemas.chats import ChatMessageCreateRequest
            message_data = ChatMessageCreateRequest(
                content={"text": "Hello, how are you?"},
                role="user"
            )
            
            # Use streaming request
            message_data = ChatMessageCreateRequest(
                content={"text": "Hello, how are you?"},
                role="user",
                response_stream=True,
                use_rag=False
            )
            
            result = await post_message(
                "chat123", message_data, self.mock_session, self.mock_user
            )
            
            # Assertions - streaming returns StreamingResponse
            from fastapi.responses import StreamingResponse
            assert isinstance(result, StreamingResponse)
            
            # Verify calls
            mock_repo.get.assert_called_once_with("chat123")
    
    @pytest.mark.asyncio
    async def test_post_message_stream_chat_not_found(self):
        """Test send streaming message with non-existent chat ID"""
        from app.api.schemas.chats import ChatMessageCreateRequest
        
        message_data = ChatMessageCreateRequest(
            content={"text": "Hello, how are you?"},
            role="user",
            response_stream=True,
            use_rag=False
        )
        
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                await post_message(
                    "nonexistent", message_data, self.mock_session, self.mock_user
                )
            
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "not_found"
    
    def test_delete_chat_success(self):
        """Test successful chat deletion"""
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = self.mock_chat
            mock_repo.delete.return_value = None
            
            # Call function
            result = delete_chat("chat123", self.mock_session, self.mock_user)
            
            # Assertions
            assert result["id"] == "chat123"
            assert result["deleted"] is True
            
            # Verify calls
            mock_repo.get.assert_called_once_with("chat123")
            mock_repo.delete.assert_called_once_with("chat123")
    
    def test_delete_chat_not_found(self):
        """Test delete chat with non-existent ID"""
        with patch('app.api.routers.chats.ChatsRepository') as mock_repo_class:
            # Setup mocks
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.get.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                delete_chat("nonexistent", self.mock_session, self.mock_user)
            
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "not_found"
