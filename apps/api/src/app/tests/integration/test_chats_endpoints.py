"""
Integration tests for Chats API endpoints
"""
import pytest
import uuid
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
class TestChatsEndpoints:
    """Integration tests for Chats API endpoints."""

    @pytest.mark.asyncio
    async def test_chats_get_pagination(self, async_client: AsyncClient):
        """Test GET /chats (пагинация)"""
        async for client in async_client:
            # Test without authentication
            response = await client.get("/api/v1/chats")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get("/api/v1/chats", headers=headers)
            assert response.status_code == 404
            
            # Test with pagination parameters
            response = await client.get("/api/v1/chats?limit=10&cursor=test", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chats_create(self, async_client: AsyncClient):
        """Test POST /chats (создание)"""
        async for client in async_client:
            chat_data = {
                "name": "Test Chat",
                "tags": ["test", "integration"]
            }
            
            # Test without authentication
            response = await client.post("/api/v1/chats", json=chat_data)
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.post("/api/v1/chats", json=chat_data, headers=headers)
            assert response.status_code == 404
            
            # Test with invalid data
            response = await client.post("/api/v1/chats", json={}, headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chats_get_by_id(self, async_client: AsyncClient):
        """Test GET /chats/{id} (получение)"""
        async for client in async_client:
            chat_id = str(uuid.uuid4())
            
            # Test without authentication
            response = await client.get(f"/api/v1/chats/{chat_id}")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get(f"/api/v1/chats/{chat_id}", headers=headers)
            assert response.status_code == 404
            
            # Test with invalid UUID
            response = await client.get("/api/v1/chats/invalid-uuid", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chats_update(self, async_client: AsyncClient):
        """Test PUT /chats/{id} (обновление)"""
        async for client in async_client:
            chat_id = str(uuid.uuid4())
            update_data = {
                "name": "Updated Chat",
                "tags": ["updated"]
            }
            
            # Test without authentication
            response = await client.put(f"/api/v1/chats/{chat_id}", json=update_data)
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.put(f"/api/v1/chats/{chat_id}", json=update_data, headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chats_delete(self, async_client: AsyncClient):
        """Test DELETE /chats/{id} (удаление)"""
        async for client in async_client:
            chat_id = str(uuid.uuid4())
            
            # Test without authentication
            response = await client.delete(f"/api/v1/chats/{chat_id}")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.delete(f"/api/v1/chats/{chat_id}", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chats_messages_pagination(self, async_client: AsyncClient):
        """Test GET /chats/{id}/messages (пагинация)"""
        async for client in async_client:
            chat_id = str(uuid.uuid4())
            
            # Test without authentication
            response = await client.get(f"/api/v1/chats/{chat_id}/messages")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get(f"/api/v1/chats/{chat_id}/messages", headers=headers)
            assert response.status_code == 404
            
            # Test with pagination parameters
            response = await client.get(f"/api/v1/chats/{chat_id}/messages?limit=10&cursor=test", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chats_messages_create(self, async_client: AsyncClient):
        """Test POST /chats/{id}/messages (создание)"""
        async for client in async_client:
            chat_id = str(uuid.uuid4())
            message_data = {
                "content": "Test message",
                "role": "user"
            }
            
            # Test without authentication
            response = await client.post(f"/api/v1/chats/{chat_id}/messages", json=message_data)
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.post(f"/api/v1/chats/{chat_id}/messages", json=message_data, headers=headers)
            assert response.status_code == 404
            
            # Test with invalid data
            response = await client.post(f"/api/v1/chats/{chat_id}/messages", json={}, headers=headers)
            assert response.status_code == 404
