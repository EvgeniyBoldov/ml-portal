"""
Tests for critical runtime fixes
"""
import pytest
import uuid
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from app.schemas.chats import ChatMessageCreateRequest
from app.repositories.factory import RepositoryFactory
from app.repositories.chats_repo import ChatsRepository, ChatMessagesRepository


class TestChatContentSchema:
    """Test chat content schema fixes"""
    
    def test_content_field_always_dict(self):
        """Test that content field always returns dict format"""
        request = ChatMessageCreateRequest(
            role="user",
            content="Hello, World!"
        )
        
        assert isinstance(request.content, dict)
        assert request.content["text"] == "Hello, World!"
        assert request.content["type"] == "text"
    
    def test_content_field_dict_input(self):
        """Test that dict input is preserved"""
        content_dict = {"text": "Hello", "type": "text", "meta": {"source": "user"}}
        request = ChatMessageCreateRequest(
            role="user",
            content=content_dict
        )
        
        assert isinstance(request.content, dict)
        assert request.content["text"] == "Hello"
        assert request.content["type"] == "text"
        assert request.content["meta"]["source"] == "user"


class TestRepositoryFactoryTenantInjection:
    """Test repository factory tenant injection"""
    
    def test_repository_factory_injects_tenant_id(self):
        """Test that RepositoryFactory properly injects tenant_id"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mock_session = Mock(spec=Session)
        
        factory = RepositoryFactory(mock_session, tenant_id, user_id)
        
        # Test chats repository
        chats_repo = factory.get_chats_repository()
        assert isinstance(chats_repo, ChatsRepository)
        assert chats_repo.tenant_id == tenant_id
        assert chats_repo.user_id == user_id
        
        # Test chat messages repository
        messages_repo = factory.get_chat_messages_repository()
        assert isinstance(messages_repo, ChatMessagesRepository)
        assert messages_repo.tenant_id == tenant_id
        assert messages_repo.user_id == user_id