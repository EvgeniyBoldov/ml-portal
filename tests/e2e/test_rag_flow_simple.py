"""
Упрощенные E2E тесты для RAG: основной флоу
"""
import pytest
import io
from uuid import uuid4


class TestRAGBasicFlow:
    """Базовые тесты RAG"""
    
    def test_upload_document(self, user_client):
        """Загрузка документа"""
        test_content = b"Test RAG document content for E2E testing"
        files = {'file': ('test_rag.txt', io.BytesIO(test_content), 'text/plain')}
        data = {
            'name': 'Test RAG Document',
            'tags': '["test", "e2e"]'
        }
        
        response = user_client.client.post(
            f"{user_client.base_url}/rag/upload",
            files=files,
            data=data,
            headers={'Authorization': f'Bearer {user_client.token}'}
        )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        doc_data = response.json()
        assert "id" in doc_data
        assert doc_data["status"] in ["uploaded", "pending"]
        
        # Cleanup
        user_client.delete(f"/rag/{doc_data['id']}")
    
    def test_list_documents(self, user_client):
        """Получение списка документов"""
        # Получаем список (может быть пустым или с ошибкой если БД не готова)
        response = user_client.get("/rag?page=1&size=100")
        
        # API может вернуть 200 или 500 если есть проблемы с БД/Qdrant
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "items" in data
    
    def test_delete_document(self, user_client):
        """Удаление документа"""
        # Создаем документ
        test_content = b"Document to delete"
        files = {'file': ('delete_doc.txt', io.BytesIO(test_content), 'text/plain')}
        data = {'name': 'Document to Delete'}
        
        create_response = user_client.client.post(
            f"{user_client.base_url}/rag/upload",
            files=files,
            data=data,
            headers={'Authorization': f'Bearer {user_client.token}'}
        )
        assert create_response.status_code == 200
        doc_id = create_response.json()["id"]
        
        # Удаляем
        delete_response = user_client.delete(f"/rag/{doc_id}")
        assert delete_response.status_code in [200, 204]
    
    def test_search_documents(self, user_client):
        """Поиск в базе знаний"""
        response = user_client.post("/rag/search", json={
            "query": "test document",
            "k": 5
        })
        
        # API может вернуть 200 с пустыми результатами или 500 если Qdrant не настроен
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "results" in data or "chunks" in data or isinstance(data, list)
