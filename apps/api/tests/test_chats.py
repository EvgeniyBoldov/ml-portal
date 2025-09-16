import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

class TestChatsAPI:
    """Test cases for chats API endpoints"""
    
    def test_create_chat_success(self, client: TestClient, test_user):
        """Test successful chat creation"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            response = client.post("/api/chats", json={
                "name": "Test Chat",
                "tags": ["test", "example"]
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "chat_id" in data
            assert isinstance(data["chat_id"], str)
    
    def test_create_chat_without_name(self, client: TestClient, test_user):
        """Test chat creation without name"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            response = client.post("/api/chats", json={
                "tags": ["test"]
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "chat_id" in data
    
    def test_create_chat_invalid_tags(self, client: TestClient, test_user):
        """Test chat creation with invalid tags"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            response = client.post("/api/chats", json={
                "name": "Test Chat",
                "tags": ["a" * 100]  # Tag too long
            })
            
            assert response.status_code == 422  # Validation error
    
    def test_list_chats(self, client: TestClient, test_user):
        """Test listing chats"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            response = client.get("/api/chats")
            
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert isinstance(data["items"], list)
    
    def test_update_chat_tags(self, client: TestClient, test_user, test_chat):
        """Test updating chat tags"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            # First create a chat
            create_response = client.post("/api/chats", json={
                "name": "Test Chat",
                "tags": ["old"]
            })
            chat_id = create_response.json()["chat_id"]
            
            # Update tags
            response = client.put(f"/api/chats/{chat_id}/tags", json={
                "tags": ["new", "updated"]
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["tags"] == ["new", "updated"]
    
    def test_send_message(self, client: TestClient, test_user, test_chat):
        """Test sending message to chat"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            # Create a chat first
            create_response = client.post("/api/chats", json={"name": "Test Chat"})
            chat_id = create_response.json()["chat_id"]
            
            # Mock LLM response
            with patch('app.services.clients.llm_chat', return_value="Test response"):
                response = client.post(f"/api/chats/{chat_id}/messages", json={
                    "content": "Hello, world!",
                    "use_rag": False,
                    "response_stream": False
                })
                
                assert response.status_code == 200
                data = response.json()
                assert "content" in data
                assert data["content"] == "Test response"
    
    def test_send_message_stream(self, client: TestClient, test_user):
        """Test sending message with streaming response"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            # Create a chat first
            create_response = client.post("/api/chats", json={"name": "Test Chat"})
            chat_id = create_response.json()["chat_id"]
            
            # Mock streaming response
            async def mock_stream():
                yield "Test "
                yield "streaming "
                yield "response"
            
            with patch('app.api.routers.chats._stream_llm_response', return_value=mock_stream()):
                response = client.post(f"/api/chats/{chat_id}/messages", json={
                    "content": "Hello, world!",
                    "use_rag": False,
                    "response_stream": True
                })
                
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    
    def test_delete_chat(self, client: TestClient, test_user):
        """Test deleting a chat"""
        with patch('app.api.deps.get_current_user', return_value=test_user):
            # Create a chat first
            create_response = client.post("/api/chats", json={"name": "Test Chat"})
            chat_id = create_response.json()["chat_id"]
            
            # Delete the chat
            response = client.delete(f"/api/chats/{chat_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["deleted"] is True
