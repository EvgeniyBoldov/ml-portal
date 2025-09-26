"""
API tests for Server-Sent Events endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.main import app


class TestSSEEndpoints:
    """Test Server-Sent Events API endpoints"""
    
    def setup_method(self):
        """Setup test method"""
        self.client = TestClient(app)
        self.test_headers = {
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json"
        }
    
    def test_sse_chat_endpoint_exists(self):
        """Test SSE chat endpoint exists"""
        response = self.client.get("/api/chats/chat123/stream")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_sse_chat_requires_auth(self):
        """Test SSE chat endpoint requires authentication"""
        response = self.client.get("/api/chats/chat123/stream")
        assert response.status_code in (401, 403)
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_authenticated(self, mock_get_current_user):
        """Test SSE chat with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            
            response = self.client.get("/api/chats/chat123/stream", headers=self.test_headers)
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_invalid_chat_id(self, mock_get_current_user):
        """Test SSE chat with invalid chat ID"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_chat.return_value = None
            
            response = self.client.get("/api/chats/invalid/stream", headers=self.test_headers)
            assert response.status_code == 404
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_access_denied(self, mock_get_current_user):
        """Test SSE chat access denied for different user"""
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
            
            response = self.client.get("/api/chats/chat123/stream", headers=self.test_headers)
            assert response.status_code == 403
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_stream_content(self, mock_get_current_user):
        """Test SSE chat stream content format"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            
            response = self.client.get("/api/chats/chat123/stream", headers=self.test_headers)
            assert response.status_code == 200
            
            # Check SSE headers
            assert response.headers["content-type"] == "text/event-stream"
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["connection"] == "keep-alive"
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_message_stream(self, mock_get_current_user):
        """Test SSE chat message streaming"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            
            # Mock streaming response
            def mock_stream():
                yield "data: {\"type\": \"message\", \"content\": \"Hello\"}\n\n"
                yield "data: {\"type\": \"message\", \"content\": \" World\"}\n\n"
                yield "data: [DONE]\n\n"
            
            mock_service_instance.stream_message.return_value = mock_stream()
            
            response = self.client.get("/api/chats/chat123/stream", headers=self.test_headers)
            assert response.status_code == 200
            
            # Check stream content
            content = response.text
            assert "data: {\"type\": \"message\", \"content\": \"Hello\"}" in content
            assert "data: {\"type\": \"message\", \"content\": \" World\"}" in content
            assert "data: [DONE]" in content
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_error_stream(self, mock_get_current_user):
        """Test SSE chat error streaming"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.stream_message.side_effect = Exception("Stream error")
            
            response = self.client.get("/api/chats/chat123/stream", headers=self.test_headers)
            assert response.status_code == 500
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_typing_indicator(self, mock_get_current_user):
        """Test SSE chat typing indicator"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            
            # Mock typing indicator stream
            def mock_typing_stream():
                yield "data: {\"type\": \"typing\", \"is_typing\": true}\n\n"
                yield "data: {\"type\": \"typing\", \"is_typing\": false}\n\n"
            
            mock_service_instance.stream_typing.return_value = mock_typing_stream()
            
            response = self.client.get("/api/chats/chat123/stream?typing=true", headers=self.test_headers)
            assert response.status_code == 200
            
            # Check typing indicator content
            content = response.text
            assert "data: {\"type\": \"typing\", \"is_typing\": true}" in content
            assert "data: {\"type\": \"typing\", \"is_typing\": false}" in content
    
    def test_sse_chat_invalid_parameters(self):
        """Test SSE chat with invalid parameters"""
        response = self.client.get("/api/chats/chat123/stream?limit=invalid")
        # Should handle invalid parameters gracefully
        assert response.status_code in (400, 422)
    
    @patch('app.api.deps.get_current_user')
    def test_sse_chat_connection_timeout(self, mock_get_current_user):
        """Test SSE chat connection timeout"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatMessagesService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            
            # Mock timeout
            def mock_timeout_stream():
                import time
                time.sleep(0.1)  # Simulate delay
                yield "data: {\"type\": \"timeout\"}\n\n"
            
            mock_service_instance.stream_message.return_value = mock_timeout_stream()
            
            response = self.client.get("/api/chats/chat123/stream", headers=self.test_headers)
            assert response.status_code == 200
