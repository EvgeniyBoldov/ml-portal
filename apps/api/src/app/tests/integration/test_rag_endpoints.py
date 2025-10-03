"""
Integration tests for RAG API endpoints
"""
import pytest
import uuid
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
class TestRAGEndpoints:
    """Integration tests for RAG API endpoints."""

    @pytest.mark.asyncio
    async def test_rag_documents_get_pagination(self, async_client: AsyncClient):
        """Test GET /rag/documents (пагинация)"""
        async for client in async_client:
            # Test without authentication
            response = await client.get("/api/v1/rag/documents")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get("/api/v1/rag/documents", headers=headers)
            assert response.status_code == 404
            
            # Test with pagination parameters
            response = await client.get("/api/v1/rag/documents?limit=10&cursor=test", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rag_documents_create(self, async_client: AsyncClient):
        """Test POST /rag/documents (создание)"""
        async for client in async_client:
            document_data = {
                "filename": "test.pdf",
                "title": "Test Document",
                "content_type": "application/pdf",
                "size": 1024
            }
            
            # Test without authentication
            response = await client.post("/api/v1/rag/documents", json=document_data)
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.post("/api/v1/rag/documents", json=document_data, headers=headers)
            assert response.status_code == 404
            
            # Test with invalid data
            response = await client.post("/api/v1/rag/documents", json={}, headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rag_documents_get_by_id(self, async_client: AsyncClient):
        """Test GET /rag/documents/{id} (получение)"""
        async for client in async_client:
            document_id = str(uuid.uuid4())
            
            # Test without authentication
            response = await client.get(f"/api/v1/rag/documents/{document_id}")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get(f"/api/v1/rag/documents/{document_id}", headers=headers)
            assert response.status_code == 404
            
            # Test with invalid UUID
            response = await client.get("/api/v1/rag/documents/invalid-uuid", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rag_documents_update(self, async_client: AsyncClient):
        """Test PUT /rag/documents/{id} (обновление)"""
        async for client in async_client:
            document_id = str(uuid.uuid4())
            update_data = {
                "title": "Updated Document",
                "tags": ["updated"]
            }
            
            # Test without authentication
            response = await client.put(f"/api/v1/rag/documents/{document_id}", json=update_data)
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.put(f"/api/v1/rag/documents/{document_id}", json=update_data, headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rag_documents_delete(self, async_client: AsyncClient):
        """Test DELETE /rag/documents/{id} (удаление)"""
        async for client in async_client:
            document_id = str(uuid.uuid4())
            
            # Test without authentication
            response = await client.delete(f"/api/v1/rag/documents/{document_id}")
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.delete(f"/api/v1/rag/documents/{document_id}", headers=headers)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rag_search(self, async_client: AsyncClient):
        """Test POST /rag/search (поиск)"""
        async for client in async_client:
            search_data = {
                "query": "test search",
                "limit": 10
            }
            
            # Test without authentication
            response = await client.post("/api/v1/rag/search", json=search_data)
            assert response.status_code == 404
            
            # Test with invalid token
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.post("/api/v1/rag/search", json=search_data, headers=headers)
            assert response.status_code == 404
            
            # Test with invalid data
            response = await client.post("/api/v1/rag/search", json={}, headers=headers)
            assert response.status_code == 404
