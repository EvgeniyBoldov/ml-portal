"""
Unified API tests for RAG endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.main_enhanced import app


class TestRAGEndpoints:
    """Test RAG API endpoints"""
    
    def setup_method(self):
        """Setup test method"""
        self.client = TestClient(app)
        self.test_headers = {
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json"
        }
    
    def test_rag_docs_requires_auth(self):
        """Test RAG docs endpoint requires authentication"""
        response = self.client.get("/api/rag/docs")
        assert response.status_code in (401, 403)
    
    def test_rag_register_requires_auth(self):
        """Test RAG register endpoint requires authentication"""
        response = self.client.post("/api/rag/docs", json={"filename": "file.pdf"})
        assert response.status_code in (401, 403)
    
    def test_rag_search_endpoint_exists(self):
        """Test RAG search endpoint exists"""
        response = self.client.post("/api/rag/search", json={"query": "hello"})
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404
    
    def test_rag_upload_requires_auth(self):
        """Test RAG upload endpoint requires authentication"""
        response = self.client.post("/api/rag/upload")
        assert response.status_code in (401, 403)
    
    def test_rag_document_get_requires_auth(self):
        """Test RAG document get endpoint requires authentication"""
        response = self.client.get("/api/rag/doc123")
        assert response.status_code in (401, 403)
    
    def test_rag_document_update_requires_auth(self):
        """Test RAG document update endpoint requires authentication"""
        response = self.client.put("/api/rag/doc123/tags", json=["tag1", "tag2"])
        assert response.status_code in (401, 403)
    
    def test_rag_document_delete_requires_auth(self):
        """Test RAG document delete endpoint requires authentication"""
        response = self.client.delete("/api/rag/doc123")
        assert response.status_code in (401, 403)
    
    def test_rag_metrics_requires_auth(self):
        """Test RAG metrics endpoint requires authentication"""
        response = self.client.get("/api/rag/metrics")
        assert response.status_code in (401, 403)
    
    @patch('app.api.deps.get_current_user')
    def test_rag_docs_list_authenticated(self, mock_get_current_user):
        """Test RAG docs list with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_user_documents.return_value = []
            
            response = self.client.get("/api/rag/docs", headers=self.test_headers)
            assert response.status_code == 200
    
    @patch('app.api.deps.get_current_user')
    def test_rag_search_authenticated(self, mock_get_current_user):
        """Test RAG search with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.search_documents.return_value = []
            
            response = self.client.post(
                "/api/rag/search",
                json={"query": "test query", "top_k": 10},
                headers=self.test_headers
            )
            assert response.status_code == 200
    
    @patch('app.api.deps.get_current_user')
    def test_rag_upload_authenticated(self, mock_get_current_user):
        """Test RAG upload with authentication"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.create_document.return_value = Mock(id="doc123")
            
            files = {"file": ("test.pdf", b"test content", "application/pdf")}
            response = self.client.post(
                "/api/rag/upload",
                files=files,
                headers={"Authorization": "Bearer test-token"}
            )
            assert response.status_code == 200
    
    def test_rag_search_validation_error(self):
        """Test RAG search with validation error"""
        response = self.client.post("/api/rag/search", json={})
        assert response.status_code == 422
    
    def test_rag_search_missing_query(self):
        """Test RAG search with missing query"""
        response = self.client.post("/api/rag/search", json={"top_k": 10})
        assert response.status_code == 422
    
    def test_rag_search_invalid_top_k(self):
        """Test RAG search with invalid top_k"""
        response = self.client.post("/api/rag/search", json={"query": "test", "top_k": -1})
        assert response.status_code == 422
    
    def test_rag_search_invalid_min_score(self):
        """Test RAG search with invalid min_score"""
        response = self.client.post("/api/rag/search", json={"query": "test", "min_score": 1.5})
        assert response.status_code == 422
    
    @patch('app.api.deps.get_current_user')
    def test_rag_document_not_found(self, mock_get_current_user):
        """Test RAG document not found"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_document.return_value = None
            
            response = self.client.get("/api/rag/doc123", headers=self.test_headers)
            assert response.status_code == 404
    
    @patch('app.api.deps.get_current_user')
    def test_rag_document_access_denied(self, mock_get_current_user):
        """Test RAG document access denied for different user"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_document = Mock()
            mock_document.user_id = "other_user"
            mock_service_instance.get_document.return_value = mock_document
            
            response = self.client.get("/api/rag/doc123", headers=self.test_headers)
            assert response.status_code == 403
