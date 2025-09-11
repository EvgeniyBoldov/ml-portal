import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import io

class TestRAGAPI:
    """Test cases for RAG API endpoints"""
    
    def test_upload_rag_file_success(self, client: TestClient):
        """Test successful RAG file upload"""
        # Create a test file
        test_file = io.BytesIO(b"Test document content")
        test_file.name = "test.txt"
        
        with patch('app.core.s3_helpers.put_object'), \
             patch('app.tasks.upload_watch.watch'):
            
            response = client.post(
                "/api/rag/upload",
                files={"file": ("test.txt", test_file, "text/plain")},
                data={"tags": '["test", "document"]'}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert data["status"] == "uploaded"
            assert data["tags"] == ["test", "document"]
    
    def test_upload_rag_file_invalid_type(self, client: TestClient):
        """Test upload with invalid file type"""
        test_file = io.BytesIO(b"Test content")
        test_file.name = "test.exe"  # Invalid extension
        
        response = client.post(
            "/api/rag/upload",
            files={"file": ("test.exe", test_file, "application/octet-stream")}
        )
        
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]
    
    def test_upload_rag_file_too_large(self, client: TestClient):
        """Test upload with file too large"""
        # Create a large file (simulate)
        large_content = b"x" * (51 * 1024 * 1024)  # 51MB
        test_file = io.BytesIO(large_content)
        test_file.name = "large.txt"
        test_file.size = 51 * 1024 * 1024
        
        response = client.post(
            "/api/rag/upload",
            files={"file": ("large.txt", test_file, "text/plain")}
        )
        
        assert response.status_code == 413
        assert "File too large" in response.json()["detail"]
    
    def test_list_rag_documents(self, client: TestClient):
        """Test listing RAG documents"""
        response = client.get("/api/rag/?page=1&size=10")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)
    
    def test_list_rag_documents_with_filters(self, client: TestClient):
        """Test listing RAG documents with filters"""
        response = client.get("/api/rag/?page=1&size=10&status=ready&search=test")
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "pagination" in data
    
    def test_get_rag_document(self, client: TestClient):
        """Test getting specific RAG document"""
        # First upload a document
        test_file = io.BytesIO(b"Test document content")
        test_file.name = "test.txt"
        
        with patch('app.core.s3_helpers.put_object'), \
             patch('app.tasks.upload_watch.watch'):
            
            upload_response = client.post(
                "/api/rag/upload",
                files={"file": ("test.txt", test_file, "text/plain")}
            )
            
            doc_id = upload_response.json()["id"]
            
            # Get the document
            response = client.get(f"/api/rag/{doc_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == doc_id
    
    def test_update_rag_document_tags(self, client: TestClient):
        """Test updating RAG document tags"""
        # First upload a document
        test_file = io.BytesIO(b"Test document content")
        test_file.name = "test.txt"
        
        with patch('app.core.s3_helpers.put_object'), \
             patch('app.tasks.upload_watch.watch'):
            
            upload_response = client.post(
                "/api/rag/upload",
                files={"file": ("test.txt", test_file, "text/plain")}
            )
            
            doc_id = upload_response.json()["id"]
            
            # Update tags
            response = client.put(f"/api/rag/{doc_id}/tags", json=["new", "tags"])
            
            assert response.status_code == 200
            data = response.json()
            assert data["tags"] == ["new", "tags"]
    
    def test_search_rag(self, client: TestClient):
        """Test RAG search"""
        with patch('app.services.rag_service.search', return_value={
            "results": [
                {
                    "id": "chunk1",
                    "document_id": "doc1",
                    "text": "Test content",
                    "score": 0.9,
                    "snippet": "Test content snippet"
                }
            ]
        }):
            response = client.post("/api/rag/search", json={
                "text": "test query",
                "top_k": 10,
                "min_score": 0.5
            })
            
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) == 1
            assert data["items"][0]["score"] == 0.9
    
    def test_rag_metrics(self, client: TestClient):
        """Test RAG metrics endpoint"""
        response = client.get("/api/rag/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_documents" in data
        assert "total_chunks" in data
        assert "storage_size_bytes" in data
        assert isinstance(data["total_documents"], int)
    
    def test_archive_rag_document(self, client: TestClient):
        """Test archiving RAG document"""
        # First upload a document
        test_file = io.BytesIO(b"Test document content")
        test_file.name = "test.txt"
        
        with patch('app.core.s3_helpers.put_object'), \
             patch('app.tasks.upload_watch.watch'):
            
            upload_response = client.post(
                "/api/rag/upload",
                files={"file": ("test.txt", test_file, "text/plain")}
            )
            
            doc_id = upload_response.json()["id"]
            
            # Archive the document
            response = client.post(f"/api/rag/{doc_id}/archive")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "archived"
    
    def test_delete_rag_document(self, client: TestClient):
        """Test deleting RAG document"""
        # First upload a document
        test_file = io.BytesIO(b"Test document content")
        test_file.name = "test.txt"
        
        with patch('app.core.s3_helpers.put_object'), \
             patch('app.tasks.upload_watch.watch'), \
             patch('app.core.s3.get_minio'):
            
            upload_response = client.post(
                "/api/rag/upload",
                files={"file": ("test.txt", test_file, "text/plain")}
            )
            
            doc_id = upload_response.json()["id"]
            
            # Delete the document
            response = client.delete(f"/api/rag/{doc_id}")
            
            assert response.status_code == 200
            data = response.json()
            assert data["deleted"] is True
