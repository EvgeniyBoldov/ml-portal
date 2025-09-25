"""
Unified API tests for chats endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.main import app


class TestChatsEndpoints:
    """Test Chats API endpoints"""
    
    def setup_method(self):
        """Setup test method"""
        self.client = TestClient(app)
        self.test_headers = {
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json"
        }
    
    def test_chats_requires_auth(self):
        """Test chats endpoint requires authentication"""
        response = self.client.get("/api/chats")
        assert response.status_code in (401, 403)
    
    def test_create_chat_requires_auth(self):
        """Test create chat endpoint requires authentication"""
        response = self.client.post("/api/chats", json={"name": "Test Chat"})
        assert response.status_code in (401, 403)
    
    def test_chat_messages_requires_auth(self):
        """Test chat messages endpoint requires authentication"""
        response = self.client.get("/api/chats/chat123/messages")
        assert response.status_code in (401, 403)
    
    def test_send_message_requires_auth(self):
        """Test send message endpoint requires authentication"""
        response = self.client.post("/api/chats/chat123/messages", json={"content": "Hello"})
        assert response.status_code in (401, 403)
    
    def test_update_chat_requires_auth(self):
        """Test update chat endpoint requires authentication"""
        response = self.client.put("/api/chats/chat123", json={"name": "Updated Chat"})
        assert response.status_code in (401, 403)
    
    def test_delete_chat_requires_auth(self):
        """Test delete chat endpoint requires authentication"""
        response = self.client.delete("/api/chats/chat123")
        assert response.status_code in (401, 403)
    
    @patch('app.api.deps.get_current_user')
    def test_chats_list_authenticated(self, mock_get_current_user):
        """Test chats list with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_user_chats.return_value = []
            
            response = self.client.get("/api/chats", headers=self.test_headers)
            assert response.status_code == 200
    
    @patch('app.api.deps.get_current_user')
    def test_create_chat_authenticated(self, mock_get_current_user):
        """Test create chat with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_chat = Mock()
            mock_chat.id = "chat123"
            mock_chat.name = "Test Chat"
            mock_service_instance.create_chat.return_value = mock_chat
            
            response = self.client.post(
                "/api/chats",
                json={"name": "Test Chat", "tags": ["work"]},
                headers=self.test_headers
            )
            assert response.status_code == 200
    
    @patch('app.api.deps.get_current_user')
    def test_chat_messages_authenticated(self, mock_get_current_user):
        """Test chat messages with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_chat_messages.return_value = []
            
            response = self.client.get("/api/chats/chat123/messages", headers=self.test_headers)
            assert response.status_code == 200
    
    @patch('app.api.deps.get_current_user')
    def test_send_message_authenticated(self, mock_get_current_user):
        """Test send message with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_message = Mock()
            mock_message.id = "msg123"
            mock_message.content = {"text": "Hello"}
            mock_service_instance.create_message.return_value = mock_message
            
            response = self.client.post(
                "/api/chats/chat123/messages",
                json={"content": "Hello", "use_rag": False},
                headers=self.test_headers
            )
            assert response.status_code == 200
    
    def test_create_chat_validation_error(self):
        """Test create chat with validation error"""
        response = self.client.post("/api/chats", json={})
        assert response.status_code == 422
    
    def test_send_message_validation_error(self):
        """Test send message with validation error"""
        response = self.client.post("/api/chats/chat123/messages", json={})
        assert response.status_code == 422
    
    def test_send_message_missing_content(self):
        """Test send message with missing content"""
        response = self.client.post("/api/chats/chat123/messages", json={"use_rag": False})
        assert response.status_code == 422
    
    @patch('app.api.deps.get_current_user')
    def test_chat_not_found(self, mock_get_current_user):
        """Test chat not found"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_chat.return_value = None
            
            response = self.client.get("/api/chats/chat123", headers=self.test_headers)
            assert response.status_code == 404
    
    @patch('app.api.deps.get_current_user')
    def test_chat_access_denied(self, mock_get_current_user):
        """Test chat access denied for different user"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_chat = Mock()
            mock_chat.owner_id = "other_user"
            mock_service_instance.get_chat.return_value = mock_chat
            
            response = self.client.get("/api/chats/chat123", headers=self.test_headers)
            assert response.status_code == 403
    
    def test_chats_pagination(self):
        """Test chats pagination parameters"""
        response = self.client.get("/api/chats?limit=10&offset=0")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_chats_cursor_pagination(self):
        """Test chats cursor pagination parameters"""
        response = self.client.get("/api/chats?limit=10&cursor=test_cursor")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_chat_messages_pagination(self):
        """Test chat messages pagination parameters"""
        response = self.client.get("/api/chats/chat123/messages?limit=10&offset=0")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_chat_messages_cursor_pagination(self):
        """Test chat messages cursor pagination parameters"""
        response = self.client.get("/api/chats/chat123/messages?limit=10&cursor=test_cursor")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
