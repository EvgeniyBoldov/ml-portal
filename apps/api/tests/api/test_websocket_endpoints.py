"""
API tests for WebSocket endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.main import app


class TestWebSocketEndpoints:
    """Test WebSocket API endpoints"""
    
    def setup_method(self):
        """Setup test method"""
        self.client = TestClient(app)
    
    def test_websocket_chat_endpoint_exists(self):
        """Test WebSocket chat endpoint exists"""
        with self.client.websocket_connect("/ws/chat/chat123") as websocket:
            # Connection should be established
            assert websocket is not None
    
    def test_websocket_chat_requires_auth(self):
        """Test WebSocket chat endpoint requires authentication"""
        with pytest.raises(Exception):  # Should fail without auth
            with self.client.websocket_connect("/ws/chat/chat123") as websocket:
                pass
    
    @patch('app.api.deps.get_current_user_websocket')
    def test_websocket_chat_authenticated(self, mock_get_current_user):
        """Test WebSocket chat with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            
            with self.client.websocket_connect("/ws/chat/chat123") as websocket:
                # Should be able to connect
                assert websocket is not None
    
    def test_websocket_chat_invalid_chat_id(self):
        """Test WebSocket chat with invalid chat ID"""
        with pytest.raises(Exception):
            with self.client.websocket_connect("/ws/chat/invalid") as websocket:
                pass
    
    @patch('app.api.deps.get_current_user_websocket')
    def test_websocket_chat_access_denied(self, mock_get_current_user):
        """Test WebSocket chat access denied for different user"""
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
            
            with pytest.raises(Exception):  # Should fail with access denied
                with self.client.websocket_connect("/ws/chat/chat123") as websocket:
                    pass
    
    @patch('app.api.deps.get_current_user_websocket')
    def test_websocket_chat_send_message(self, mock_get_current_user):
        """Test sending message via WebSocket"""
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
            
            with self.client.websocket_connect("/ws/chat/chat123") as websocket:
                # Send message
                websocket.send_json({
                    "type": "message",
                    "content": "Hello",
                    "use_rag": False
                })
                
                # Should receive response
                data = websocket.receive_json()
                assert data["type"] == "message"
                assert data["content"] == "Hello"
    
    @patch('app.api.deps.get_current_user_websocket')
    def test_websocket_chat_typing_indicator(self, mock_get_current_user):
        """Test typing indicator via WebSocket"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with self.client.websocket_connect("/ws/chat/chat123") as websocket:
            # Send typing indicator
            websocket.send_json({
                "type": "typing",
                "is_typing": True
            })
            
            # Should receive typing indicator
            data = websocket.receive_json()
            assert data["type"] == "typing"
            assert data["is_typing"] is True
    
    @patch('app.api.deps.get_current_user_websocket')
    def test_websocket_chat_invalid_message_type(self, mock_get_current_user):
        """Test WebSocket with invalid message type"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with self.client.websocket_connect("/ws/chat/chat123") as websocket:
            # Send invalid message type
            websocket.send_json({
                "type": "invalid_type",
                "content": "Hello"
            })
            
            # Should receive error
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert "Invalid message type" in data["message"]
    
    @patch('app.api.deps.get_current_user_websocket')
    def test_websocket_chat_connection_closed(self, mock_get_current_user):
        """Test WebSocket connection closed handling"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with self.client.websocket_connect("/ws/chat/chat123") as websocket:
            # Close connection
            websocket.close()
            
            # Should handle connection closed gracefully
            assert websocket.client_state.name == "DISCONNECTED"
