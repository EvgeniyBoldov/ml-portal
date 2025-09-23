"""
Performance tests for API endpoints
"""
import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.main_enhanced import app


class TestAPIPerformance:
    """Test API performance"""
    
    def setup_method(self):
        """Setup test method"""
        self.client = TestClient(app)
        self.test_headers = {
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json"
        }
    
    @patch('app.api.deps.get_current_user')
    def test_auth_endpoints_performance(self, mock_get_current_user):
        """Test authentication endpoints performance"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        # Test login performance
        start_time = time.time()
        response = self.client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "password"
        })
        end_time = time.time()
        
        # Should complete within 500ms
        assert (end_time - start_time) < 0.5
    
    @patch('app.api.deps.get_current_user')
    def test_chats_endpoints_performance(self, mock_get_current_user):
        """Test chats endpoints performance"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_user_chats.return_value = []
            
            # Test chats list performance
            start_time = time.time()
            response = self.client.get("/api/chats", headers=self.test_headers)
            end_time = time.time()
            
            # Should complete within 300ms
            assert (end_time - start_time) < 0.3
    
    @patch('app.api.deps.get_current_user')
    def test_rag_endpoints_performance(self, mock_get_current_user):
        """Test RAG endpoints performance"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_user_documents.return_value = []
            
            # Test RAG docs list performance
            start_time = time.time()
            response = self.client.get("/api/rag/docs", headers=self.test_headers)
            end_time = time.time()
            
            # Should complete within 400ms
            assert (end_time - start_time) < 0.4
    
    @patch('app.api.deps.get_current_user')
    def test_search_performance(self, mock_get_current_user):
        """Test search performance"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.search_documents.return_value = []
            
            # Test search performance
            start_time = time.time()
            response = self.client.post("/api/rag/search", json={
                "query": "test query",
                "top_k": 10
            }, headers=self.test_headers)
            end_time = time.time()
            
            # Should complete within 1 second
            assert (end_time - start_time) < 1.0
    
    def test_validation_performance(self):
        """Test validation performance"""
        # Test validation error performance
        start_time = time.time()
        response = self.client.post("/api/auth/login", json={})
        end_time = time.time()
        
        # Should complete within 100ms
        assert (end_time - start_time) < 0.1
        assert response.status_code == 422
    
    def test_error_handling_performance(self):
        """Test error handling performance"""
        # Test 404 error performance
        start_time = time.time()
        response = self.client.get("/api/nonexistent")
        end_time = time.time()
        
        # Should complete within 50ms
        assert (end_time - start_time) < 0.05
        assert response.status_code == 404
    
    @patch('app.api.deps.get_current_user')
    def test_pagination_performance(self, mock_get_current_user):
        """Test pagination performance"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_user_chats.return_value = []
            
            # Test pagination performance
            start_time = time.time()
            response = self.client.get("/api/chats?limit=50&offset=100", headers=self.test_headers)
            end_time = time.time()
            
            # Should complete within 200ms
            assert (end_time - start_time) < 0.2
    
    @patch('app.api.deps.get_current_user')
    def test_concurrent_requests_performance(self, mock_get_current_user):
        """Test concurrent requests performance"""
        mock_user = Mock()
        mock_user.id = "user123"
        mock_user.role = "reader"
        mock_get_current_user.return_value = mock_user
        
        with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
            mock_service_instance = Mock()
            mock_service.return_value = mock_service_instance
            mock_service_instance.get_user_chats.return_value = []
            
            # Test concurrent requests
            start_time = time.time()
            
            import threading
            
            def concurrent_request():
                response = self.client.get("/api/chats", headers=self.test_headers)
                assert response.status_code == 200
            
            threads = []
            for _ in range(10):
                thread = threading.Thread(target=concurrent_request)
                threads.append(thread)
                thread.start()
            
            for thread in threads:
                thread.join()
            
            end_time = time.time()
            
            # Should complete within 1 second
            assert (end_time - start_time) < 1.0
    
    def test_middleware_performance(self):
        """Test middleware performance"""
        # Test request ID middleware performance
        start_time = time.time()
        response = self.client.get("/api/health")
        end_time = time.time()
        
        # Should complete within 50ms
        assert (end_time - start_time) < 0.05
    
    def test_cors_performance(self):
        """Test CORS performance"""
        # Test CORS preflight request performance
        start_time = time.time()
        response = self.client.options("/api/chats", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST"
        })
        end_time = time.time()
        
        # Should complete within 50ms
        assert (end_time - start_time) < 0.05
    
    def test_rate_limiting_performance(self):
        """Test rate limiting performance"""
        # Test rate limiting performance
        start_time = time.time()
        
        # Make multiple requests quickly
        for _ in range(5):
            response = self.client.get("/api/health")
        
        end_time = time.time()
        
        # Should complete within 200ms
        assert (end_time - start_time) < 0.2
