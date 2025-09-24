"""
Performance tests for database operations
"""
import pytest
import time
import asyncio
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from app.core.db import DatabaseManager
from app.repositories.users_repo_enhanced import UsersRepository
from app.repositories.chats_repo_enhanced import ChatsRepository
from app.repositories.rag_repo_enhanced import RAGDocumentsRepository


class TestDatabasePerformance:
    """Test database performance"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.users_repo = UsersRepository(self.mock_session)
        self.chats_repo = ChatsRepository(self.mock_session)
        self.rag_repo = RAGDocumentsRepository(self.mock_session)
    
    def test_user_creation_performance(self):
        """Test user creation performance"""
        start_time = time.time()
        
        # Mock user creation
        with patch.object(self.users_repo, 'create_user') as mock_create:
            mock_user = Mock()
            mock_create.return_value = mock_user
            
            self.users_repo.create_user(
                login="testuser",
                password_hash="hash",
                role="reader"
            )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 100ms
        assert execution_time < 0.1
    
    def test_user_search_performance(self):
        """Test user search performance"""
        start_time = time.time()
        
        # Mock user search
        with patch.object(self.users_repo, 'search_users') as mock_search:
            mock_search.return_value = []
            
            self.users_repo.search_users("test", limit=50)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 200ms
        assert execution_time < 0.2
    
    def test_chat_creation_performance(self):
        """Test chat creation performance"""
        start_time = time.time()
        
        # Mock chat creation
        with patch.object(self.chats_repo, 'create_chat') as mock_create:
            mock_chat = Mock()
            mock_create.return_value = mock_chat
            
            self.chats_repo.create_chat(
                owner_id="user123",
                name="Test Chat"
            )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 100ms
        assert execution_time < 0.1
    
    def test_chat_messages_list_performance(self):
        """Test chat messages list performance"""
        start_time = time.time()
        
        # Mock chat messages list
        with patch('app.repositories.chats_repo_enhanced.ChatsRepository.get_chat_messages') as mock_get:
            mock_get.return_value = []
            
            self.chats_repo.get_chat_messages("chat123", limit=50)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 200ms
        assert execution_time < 0.2
    
    def test_rag_document_creation_performance(self):
        """Test RAG document creation performance"""
        start_time = time.time()
        
        # Mock RAG document creation
        with patch.object(self.rag_repo, 'create_document') as mock_create:
            mock_doc = Mock()
            mock_create.return_value = mock_doc
            
            self.rag_repo.create_document(
                filename="test.pdf",
                title="Test Document",
                user_id="user123"
            )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 100ms
        assert execution_time < 0.1
    
    def test_rag_document_search_performance(self):
        """Test RAG document search performance"""
        start_time = time.time()
        
        # Mock RAG document search
        with patch.object(self.rag_repo, 'search_documents') as mock_search:
            mock_search.return_value = []
            
            self.rag_repo.search_documents("user123", "test query")
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 300ms
        assert execution_time < 0.3
    
    def test_bulk_operations_performance(self):
        """Test bulk operations performance"""
        start_time = time.time()
        
        # Mock bulk user creation
        with patch.object(self.users_repo, 'create') as mock_create:
            mock_create.return_value = Mock()
            
            # Create 100 users
            for i in range(100):
                self.users_repo.create(
                    login=f"user{i}",
                    password_hash="hash",
                    role="reader"
                )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 1 second
        assert execution_time < 1.0
    
    def test_concurrent_operations_performance(self):
        """Test concurrent operations performance"""
        start_time = time.time()
        
        # Mock concurrent operations
        with patch.object(self.users_repo, 'get_by_id') as mock_get:
            mock_get.return_value = Mock()
            
            # Simulate concurrent operations
            import threading
            
            def concurrent_operation():
                self.users_repo.get_by_id("user123")
            
            threads = []
            for _ in range(10):
                thread = threading.Thread(target=concurrent_operation)
                threads.append(thread)
                thread.start()
            
            for thread in threads:
                thread.join()
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 500ms
        assert execution_time < 0.5
    
    def test_database_connection_pool_performance(self):
        """Test database connection pool performance"""
        start_time = time.time()
        
        # Mock database manager
        with patch('app.core.db.db_manager') as mock_db_manager:
            mock_session = Mock()
            mock_db_manager.get_session.return_value.__enter__.return_value = mock_session
            
            # Simulate multiple connections
            for _ in range(20):
                with mock_db_manager.get_session() as session:
                    pass
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 200ms
        assert execution_time < 0.2
    
    def test_query_optimization_performance(self):
        """Test query optimization performance"""
        start_time = time.time()
        
        # Mock optimized query
        with patch.object(self.chats_repo, 'get_user_chats') as mock_get:
            mock_get.return_value = []
            
            # Simulate optimized query with filters and pagination
            self.chats_repo.get_user_chats(
                user_id="user123",
                query="test",
                limit=20,
                offset=0
            )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete within 150ms
        assert execution_time < 0.15
