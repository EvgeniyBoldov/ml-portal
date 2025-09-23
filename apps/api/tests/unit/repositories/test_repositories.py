"""
Tests for enhanced repositories
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
import uuid
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.repositories.users_repo_enhanced import (
    UsersRepository, UserTokensRepository, UserRefreshTokensRepository,
    PasswordResetTokensRepository, AuditLogsRepository
)
from app.repositories.chats_repo_enhanced import (
    ChatsRepository, ChatMessagesRepository
)
from app.repositories.rag_repo_enhanced import (
    RAGDocumentsRepository, RAGChunksRepository
)
from app.models.user import Users, UserTokens, UserRefreshTokens, PasswordResetTokens, AuditLogs
from app.models.chat import Chats, ChatMessages
from app.models.rag import RAGDocument, RAGChunk


class TestUsersRepository:
    """Test enhanced users repository"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.repo = UsersRepository(self.mock_session)
    
    def test_create_user_success(self):
        """Test successful user creation"""
        with patch.object(self.repo, 'get_by_login') as mock_get_login:
            with patch.object(self.repo, 'get_by_email') as mock_get_email:
                with patch.object(self.repo, 'create') as mock_create:
                    mock_get_login.return_value = None
                    mock_get_email.return_value = None
                    mock_user = Mock()
                    mock_create.return_value = mock_user
                    
                    result = self.repo.create_user(
                        login="testuser",
                        password_hash="hash123",
                        role="reader",
                        email="test@example.com"
                    )
                    
                    assert result == mock_user
                    mock_create.assert_called_once()
    
    def test_create_user_duplicate_login(self):
        """Test user creation with duplicate login"""
        with patch.object(self.repo, 'get_by_login') as mock_get_login:
            mock_get_login.return_value = Mock()  # User exists
            
            with pytest.raises(ValueError, match="User with login 'testuser' already exists"):
                self.repo.create_user("testuser", "hash123")
    
    def test_create_user_duplicate_email(self):
        """Test user creation with duplicate email"""
        with patch.object(self.repo, 'get_by_login') as mock_get_login:
            with patch.object(self.repo, 'get_by_email') as mock_get_email:
                mock_get_login.return_value = None
                mock_get_email.return_value = Mock()  # Email exists
                
                with pytest.raises(ValueError, match="User with email 'test@example.com' already exists"):
                    self.repo.create_user("testuser", "hash123", email="test@example.com")
    
    def test_get_by_login(self):
        """Test get user by login"""
        with patch.object(self.repo, 'get_by_field') as mock_get_field:
            mock_user = Mock()
            mock_get_field.return_value = mock_user
            
            result = self.repo.get_by_login("testuser")
            
            assert result == mock_user
            mock_get_field.assert_called_once_with('login', 'testuser')
    
    def test_get_by_email(self):
        """Test get user by email"""
        with patch.object(self.repo, 'get_by_field') as mock_get_field:
            mock_user = Mock()
            mock_get_field.return_value = mock_user
            
            result = self.repo.get_by_email("test@example.com")
            
            assert result == mock_user
            mock_get_field.assert_called_once_with('email', 'test@example.com')
    
    def test_get_active_users(self):
        """Test get active users"""
        with patch.object(self.repo, 'list') as mock_list:
            mock_users = [Mock(), Mock()]
            mock_list.return_value = mock_users
            
            result = self.repo.get_active_users()
            
            assert result == mock_users
            mock_list.assert_called_once_with(filters={'is_active': True})
    
    def test_update_user_role(self):
        """Test update user role"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_user = Mock()
            mock_update.return_value = mock_user
            
            result = self.repo.update_user_role("user123", "admin")
            
            assert result == mock_user
            mock_update.assert_called_once_with("user123", role="admin")
    
    def test_deactivate_user(self):
        """Test deactivate user"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_user = Mock()
            mock_update.return_value = mock_user
            
            result = self.repo.deactivate_user("user123")
            
            assert result == mock_user
            mock_update.assert_called_once_with("user123", is_active=False)
    
    def test_activate_user(self):
        """Test activate user"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_user = Mock()
            mock_update.return_value = mock_user
            
            result = self.repo.activate_user("user123")
            
            assert result == mock_user
            mock_update.assert_called_once_with("user123", is_active=True)
    
    def test_change_password(self):
        """Test change password"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_user = Mock()
            mock_update.return_value = mock_user
            
            result = self.repo.change_password("user123", "newhash")
            
            assert result == mock_user
            mock_update.assert_called_once_with("user123", password_hash="newhash")


class TestUserTokensRepository:
    """Test user tokens repository"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.repo = UserTokensRepository(self.mock_session)
    
    def test_get_by_hash(self):
        """Test get token by hash"""
        with patch.object(self.repo, 'get_by_field') as mock_get_field:
            mock_token = Mock()
            mock_get_field.return_value = mock_token
            
            result = self.repo.get_by_hash("tokenhash123")
            
            assert result == mock_token
            mock_get_field.assert_called_once_with('token_hash', 'tokenhash123')
    
    def test_get_user_tokens(self):
        """Test get user tokens"""
        with patch.object(self.repo, 'list') as mock_list:
            mock_tokens = [Mock(), Mock()]
            mock_list.return_value = mock_tokens
            
            result = self.repo.get_user_tokens("user123")
            
            assert result == mock_tokens
            mock_list.assert_called_once_with(
                filters={'user_id': 'user123', 'revoked_at': None},
                order_by='-created_at'
            )
    
    def test_create_token(self):
        """Test create token"""
        with patch.object(self.repo, 'create') as mock_create:
            mock_token = Mock()
            mock_create.return_value = mock_token
            
            result = self.repo.create_token(
                user_id="user123",
                token_hash="hash123",
                name="test_token",
                scopes=["read", "write"]
            )
            
            assert result == mock_token
            mock_create.assert_called_once()
    
    def test_revoke_token(self):
        """Test revoke token"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_token = Mock()
            mock_update.return_value = mock_token
            
            result = self.repo.revoke_token("token123")
            
            assert result is True
            mock_update.assert_called_once()
    
    def test_is_token_valid(self):
        """Test token validation"""
        with patch.object(self.repo, 'get_by_hash') as mock_get_by_hash:
            # Valid token
            mock_token = Mock()
            mock_token.revoked_at = None
            mock_token.expires_at = datetime.now(timezone.utc).replace(year=2030)
            mock_get_by_hash.return_value = mock_token
            
            result = self.repo.is_token_valid("tokenhash123")
            assert result is True
            
            # Revoked token
            mock_token.revoked_at = datetime.now(timezone.utc)
            result = self.repo.is_token_valid("tokenhash123")
            assert result is False
            
            # Expired token
            mock_token.revoked_at = None
            mock_token.expires_at = datetime.now(timezone.utc).replace(year=2020)
            result = self.repo.is_token_valid("tokenhash123")
            assert result is False


class TestChatsRepository:
    """Test enhanced chats repository"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.repo = ChatsRepository(self.mock_session)
    
    def test_create_chat(self):
        """Test create chat"""
        with patch.object(self.repo, 'create') as mock_create:
            mock_chat = Mock()
            mock_create.return_value = mock_chat
            
            result = self.repo.create_chat(
                owner_id="user123",
                name="Test Chat",
                tags=["work", "important"]
            )
            
            assert result == mock_chat
            mock_create.assert_called_once()
    
    def test_get_user_chats(self):
        """Test get user chats"""
        with patch.object(self.repo, 'list') as mock_list:
            mock_chats = [Mock(), Mock()]
            mock_list.return_value = mock_chats
            
            result = self.repo.get_user_chats("user123")
            
            assert result == mock_chats
            mock_list.assert_called_once()
    
    def test_get_user_chats_with_query(self):
        """Test get user chats with search query"""
        with patch.object(self.repo, 'search') as mock_search:
            mock_chats = [Mock(), Mock()]
            mock_chats[0].owner_id = "user123"
            mock_chats[1].owner_id = "user123"
            mock_search.return_value = mock_chats
            
            result = self.repo.get_user_chats("user123", query="test")
            
            assert result == mock_chats
            mock_search.assert_called_once_with("test", ['name'], 100)
    
    def test_update_chat_name(self):
        """Test update chat name"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_chat = Mock()
            mock_update.return_value = mock_chat
            
            result = self.repo.update_chat_name("chat123", "New Name")
            
            assert result == mock_chat
            mock_update.assert_called_once_with("chat123", name="New Name")
    
    def test_update_chat_tags(self):
        """Test update chat tags"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_chat = Mock()
            mock_update.return_value = mock_chat
            
            result = self.repo.update_chat_tags("chat123", ["tag1", "tag2"])
            
            assert result == mock_chat
            mock_update.assert_called_once_with("chat123", tags=["tag1", "tag2"])


class TestChatMessagesRepository:
    """Test chat messages repository"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.repo = ChatMessagesRepository(self.mock_session)
    
    def test_create_message(self):
        """Test create message"""
        with patch.object(self.repo, 'create') as mock_create:
            with patch('app.repositories.chats_repo_enhanced.ChatsRepository') as mock_chats_repo:
                mock_message = Mock()
                mock_create.return_value = mock_message
                mock_chats_repo.return_value.update_last_message_at.return_value = None
                
                result = self.repo.create_message(
                    chat_id="chat123",
                    role="user",
                    content={"text": "Hello world"},
                    model="gpt-4"
                )
                
                assert result == mock_message
                mock_create.assert_called_once()
    
    def test_get_chat_messages(self):
        """Test get chat messages"""
        with patch.object(self.repo.session, 'execute') as mock_execute:
            mock_result = Mock()
            mock_messages = [Mock(), Mock()]
            mock_result.scalars.return_value.all.return_value = mock_messages
            mock_execute.return_value = mock_result
            
            result, next_cursor = self.repo.get_chat_messages("chat123")
            
            assert result == mock_messages
            assert next_cursor is None
            mock_execute.assert_called_once()
    
    def test_get_messages_by_role(self):
        """Test get messages by role"""
        with patch.object(self.repo, 'list') as mock_list:
            mock_messages = [Mock()]
            mock_list.return_value = mock_messages
            
            result = self.repo.get_messages_by_role("chat123", "user")
            
            assert result == mock_messages
            mock_list.assert_called_once_with(
                filters={'chat_id': 'chat123', 'role': 'user'},
                order_by='created_at',
                limit=50
            )
    
    def test_count_messages(self):
        """Test count messages"""
        with patch.object(self.repo, 'count') as mock_count:
            mock_count.return_value = 5
            
            result = self.repo.count_messages("chat123")
            
            assert result == 5
            mock_count.assert_called_once_with(filters={'chat_id': 'chat123'})


class TestRAGDocumentsRepository:
    """Test RAG documents repository"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.repo = RAGDocumentsRepository(self.mock_session)
    
    def test_create_document(self):
        """Test create document"""
        with patch.object(self.repo, 'create') as mock_create:
            mock_doc = Mock()
            mock_create.return_value = mock_doc
            
            result = self.repo.create_document(
                filename="test.pdf",
                title="Test Document",
                user_id="user123",
                content_type="application/pdf"
            )
            
            assert result == mock_doc
            mock_create.assert_called_once()
    
    def test_get_user_documents(self):
        """Test get user documents"""
        with patch.object(self.repo, 'list') as mock_list:
            mock_docs = [Mock(), Mock()]
            mock_list.return_value = mock_docs
            
            result = self.repo.get_user_documents("user123")
            
            assert result == mock_docs
            mock_list.assert_called_once()
    
    def test_update_document_status(self):
        """Test update document status"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_doc = Mock()
            mock_update.return_value = mock_doc
            
            result = self.repo.update_document_status("doc123", "processed")
            
            assert result == mock_doc
            mock_update.assert_called_once()
    
    def test_get_document_stats(self):
        """Test get document stats"""
        with patch.object(self.repo, 'count') as mock_count:
            mock_count.side_effect = [10, 8, 1, 1]  # total, processed, processing, failed
            
            result = self.repo.get_document_stats("user123")
            
            expected = {
                'total': 10,
                'processed': 8,
                'processing': 1,
                'failed': 1
            }
            assert result == expected


class TestRAGChunksRepository:
    """Test RAG chunks repository"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.repo = RAGChunksRepository(self.mock_session)
    
    def test_create_chunk(self):
        """Test create chunk"""
        with patch.object(self.repo, 'create') as mock_create:
            mock_chunk = Mock()
            mock_create.return_value = mock_chunk
            
            result = self.repo.create_chunk(
                document_id="doc123",
                content="This is a test chunk",
                chunk_index=0,
                embedding=[0.1, 0.2, 0.3]
            )
            
            assert result == mock_chunk
            mock_create.assert_called_once()
    
    def test_get_document_chunks(self):
        """Test get document chunks"""
        with patch.object(self.repo, 'list') as mock_list:
            mock_chunks = [Mock(), Mock()]
            mock_list.return_value = mock_chunks
            
            result = self.repo.get_document_chunks("doc123")
            
            assert result == mock_chunks
            mock_list.assert_called_once()
    
    def test_update_chunk_embedding(self):
        """Test update chunk embedding"""
        with patch.object(self.repo, 'update') as mock_update:
            mock_chunk = Mock()
            mock_update.return_value = mock_chunk
            
            result = self.repo.update_chunk_embedding(
                "chunk123",
                [0.1, 0.2, 0.3],
                "vector123"
            )
            
            assert result == mock_chunk
            mock_update.assert_called_once()
    
    def test_count_document_chunks(self):
        """Test count document chunks"""
        with patch.object(self.repo, 'count') as mock_count:
            mock_count.return_value = 5
            
            result = self.repo.count_document_chunks("doc123")
            
            assert result == 5
            mock_count.assert_called_once_with(filters={'document_id': 'doc123'})


if __name__ == "__main__":
    pytest.main([__file__])
