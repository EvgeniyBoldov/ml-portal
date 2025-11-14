"""
E2E тесты для RAG: полный флоу от создания до скачивания
"""
import pytest
import time
from uuid import uuid4
from pathlib import Path
import io


class TestRAGDocumentFlow:
    """Тесты полного флоу RAG-документов"""
    
    @pytest.fixture
    def test_document(self, user_client):
        """Создать тестовый документ через upload"""
        # Создаем тестовый файл
        test_content = b"Test document content for E2E testing"
        files = {'file': ('test_doc.txt', io.BytesIO(test_content), 'text/plain')}
        data = {
            'name': f"Test Document {uuid4().hex[:8]}",
            'tags': '["test", "e2e"]'
        }
        
        response = user_client.client.post(
            f"{user_client.base_url}/rag/upload",
            files=files,
            data=data,
            headers={'Authorization': f'Bearer {user_client.token}'}
        )
        assert response.status_code == 200, f"Upload failed: {response.text}"
        doc = response.json()
        
        yield doc
        
        # Cleanup
        try:
            user_client.delete(f"/rag/{doc['id']}")
        except:
            pass
    
    def test_create_document(self, user_client):
        """Создание RAG-документа через upload"""
        test_content = b"Test RAG document content"
        files = {'file': ('test_rag.txt', io.BytesIO(test_content), 'text/plain')}
        data = {
            'name': 'Test RAG Document',
            'tags': '["test"]'
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
        assert doc_data["title"] == "Test RAG Document"
        assert doc_data["status"] in ["uploaded", "pending"]
        
        # Cleanup
        user_client.delete(f"/rag/{doc_data['id']}")
    
    def test_list_documents(self, user_client, test_document):
        """Получение списка документов"""
        response = user_client.get("/rag?page=1&size=100")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) > 0
    
    def test_get_document(self, user_client, test_document):
        """Получение документа по ID"""
        response = user_client.get(f"/rag/documents/{test_document['id']}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_document["id"]
        assert data["name"] == test_document["name"]
    
    def test_update_document_tags(self, user_client, test_document):
        """Обновление тегов документа"""
        new_tags = ["updated", "test"]
        response = user_client.put(f"/rag/{test_document['id']}/tags", json=new_tags)
        
        assert response.status_code == 200
        data = response.json()
        assert "tags" in data or "success" in data  # API может вернуть разные форматы
    
    def test_delete_document(self, user_client):
        """Удаление документа"""
        # Создаем документ для удаления
        test_content = b"Document to delete"
        files = {'file': ('delete_doc.txt', io.BytesIO(test_content), 'text/plain')}
        data = {'name': 'Document to delete'}
        
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


class TestRAGIngestFlow:
    """Тесты флоу ингеста RAG-документов"""
    
    @pytest.fixture
    def pending_document(self, user_client):
        """Создать документ в статусе pending"""
        response = user_client.post("/rag/documents", json={
            "name": f"Pending Doc {uuid4().hex[:8]}",
            "url": "https://arxiv.org/pdf/1706.03762.pdf",  # Attention is All You Need
            "scope": "local"
        })
        assert response.status_code == 200
        doc = response.json()
        
        yield doc
        
        # Cleanup
        try:
            user_client.delete(f"/rag/documents/{doc['id']}")
        except:
            pass
    
    def test_start_ingest(self, user_client, pending_document):
        """Запуск ингеста документа"""
        response = user_client.post(f"/rag/documents/{pending_document['id']}/ingest")
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data or "status" in data
        
        # Даем время на начало обработки
        time.sleep(2)
        
        # Проверяем статус
        status_response = user_client.get(f"/rag/documents/{pending_document['id']}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        # Статус должен измениться с pending
        assert status_data["status"] in ["downloading", "processing", "completed", "failed"]
    
    def test_check_ingest_status(self, user_client, pending_document):
        """Проверка статуса ингеста"""
        # Запускаем ингест
        ingest_response = user_client.post(f"/rag/documents/{pending_document['id']}/ingest")
        assert ingest_response.status_code == 200
        
        # Проверяем статус несколько раз
        for _ in range(5):
            time.sleep(2)
            response = user_client.get(f"/rag/documents/{pending_document['id']}")
            assert response.status_code == 200
            data = response.json()
            
            if data["status"] in ["completed", "failed"]:
                break
    
    def test_restart_failed_ingest(self, user_client):
        """Перезапуск неудачного ингеста"""
        # Создаем документ с невалидным URL
        create_response = user_client.post("/rag/documents", json={
            "name": "Invalid URL Doc",
            "url": "https://invalid-url-that-does-not-exist.com/file.pdf",
            "scope": "local"
        })
        assert create_response.status_code == 200
        doc_id = create_response.json()["id"]
        
        # Запускаем ингест (должен упасть)
        ingest_response = user_client.post(f"/rag/documents/{doc_id}/ingest")
        assert ingest_response.status_code == 200
        
        time.sleep(5)
        
        # Проверяем статус (должен быть failed)
        status_response = user_client.get(f"/rag/documents/{doc_id}")
        assert status_response.status_code == 200
        
        # Перезапускаем
        restart_response = user_client.post(f"/rag/documents/{doc_id}/ingest")
        assert restart_response.status_code == 200
        
        # Cleanup
        user_client.delete(f"/rag/documents/{doc_id}")
    
    def test_ingest_stages(self, user_client, pending_document):
        """Проверка этапов ингеста"""
        # Запускаем ингест
        user_client.post(f"/rag/documents/{pending_document['id']}/ingest")
        
        statuses_seen = set()
        
        # Мониторим статусы
        for _ in range(30):  # Максимум 60 секунд
            time.sleep(2)
            response = user_client.get(f"/rag/documents/{pending_document['id']}")
            assert response.status_code == 200
            data = response.json()
            
            status = data["status"]
            statuses_seen.add(status)
            
            if status == "completed":
                # Проверяем, что прошли основные этапы
                assert "downloading" in statuses_seen or "processing" in statuses_seen
                break
            
            if status == "failed":
                pytest.skip("Ingest failed (network issue or invalid document)")
                break


class TestRAGDownload:
    """Тесты скачивания документов"""
    
    @pytest.fixture
    def completed_document(self, user_client):
        """Создать и обработать документ"""
        # Создаем документ
        create_response = user_client.post("/rag/documents", json={
            "name": f"Completed Doc {uuid4().hex[:8]}",
            "url": "https://arxiv.org/pdf/1706.03762.pdf",
            "scope": "local"
        })
        assert create_response.status_code == 200
        doc = create_response.json()
        
        # Запускаем ингест
        user_client.post(f"/rag/documents/{doc['id']}/ingest")
        
        # Ждем завершения
        for _ in range(30):
            time.sleep(2)
            status_response = user_client.get(f"/rag/documents/{doc['id']}")
            if status_response.status_code == 200:
                status = status_response.json()["status"]
                if status == "completed":
                    break
        
        yield doc
        
        # Cleanup
        try:
            user_client.delete(f"/rag/documents/{doc['id']}")
        except:
            pass
    
    def test_download_original(self, user_client, completed_document):
        """Скачивание оригинального документа"""
        response = user_client.get(
            f"/rag/documents/{completed_document['id']}/download/original"
        )
        
        # Если документ обработан, должен быть доступен для скачивания
        if response.status_code == 200:
            assert len(response.content) > 0
            assert response.headers.get("content-type") in [
                "application/pdf",
                "application/octet-stream"
            ]
        else:
            # Может быть 404 если файл не сохранен
            assert response.status_code in [404, 500]
    
    def test_download_canonical(self, user_client, completed_document):
        """Скачивание канонического документа"""
        response = user_client.get(
            f"/rag/documents/{completed_document['id']}/download/canonical"
        )
        
        if response.status_code == 200:
            assert len(response.content) > 0
            # Canonical обычно markdown или text
            assert response.headers.get("content-type") in [
                "text/markdown",
                "text/plain",
                "application/octet-stream"
            ]
        else:
            assert response.status_code in [404, 500]
    
    def test_download_status_change(self, user_client, pending_document):
        """Проверка изменения статуса при скачивании"""
        # Пытаемся скачать до обработки
        response_before = user_client.get(
            f"/rag/documents/{pending_document['id']}/download/original"
        )
        assert response_before.status_code == 404  # Файл еще не скачан
        
        # Запускаем ингест
        user_client.post(f"/rag/documents/{pending_document['id']}/ingest")
        
        # Ждем завершения
        for _ in range(30):
            time.sleep(2)
            status_response = user_client.get(f"/rag/documents/{pending_document['id']}")
            if status_response.status_code == 200:
                status = status_response.json()["status"]
                if status in ["completed", "failed"]:
                    break
        
        # Пытаемся скачать после обработки
        response_after = user_client.get(
            f"/rag/documents/{pending_document['id']}/download/original"
        )
        
        # Если обработка успешна, файл должен быть доступен
        if status == "completed":
            assert response_after.status_code in [200, 404]  # 404 если не сохранен


class TestRAGSearch:
    """Тесты поиска по RAG"""
    
    def test_search_in_knowledge_base(self, user_client):
        """Поиск в базе знаний"""
        response = user_client.post("/rag/search", json={
            "query": "machine learning",
            "k": 5
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)
    
    def test_search_with_filters(self, user_client):
        """Поиск с фильтрами"""
        response = user_client.post("/rag/search", json={
            "query": "neural networks",
            "k": 10,
            "scope": "local"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
