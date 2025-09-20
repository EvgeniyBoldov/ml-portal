"""
Tests for enhanced services (fixed version)
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import uuid
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.services.users_service_enhanced import UsersService, AsyncUsersService
from app.services.chats_service_enhanced import ChatsService, ChatMessagesService, AsyncChatsService
from app.services.rag_service_enhanced import RAGDocumentsService, RAGChunksService, AsyncRAGDocumentsService
from app.models.user import Users, UserTokens
from app.models.chat import Chats, ChatMessages
from app.models.rag import RAGDocument, RAGChunk


class TestUsersService:
    """Test enhanced users service"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.service = UsersService(self.mock_session)
    
    def test_create_user_success(self):
        """Test successful user creation"""
        with patch.object(self.service.users_repo, 'get_by_login') as mock_get_login:
            with patch.object(self.service.users_repo, 'get_by_email') as mock_get_email:
                with patch.object(self.service.users_repo, 'create_user') as mock_create:
                    with patch.object(self.service, '_hash_password') as mock_hash:
                        with patch.object(self.service.audit_repo, 'create_log') as mock_audit:
                            mock_get_login.return_value = None
                            mock_get_email.return_value = None
                            mock_hash.return_value = "hashed_password"
                            
                            mock_user = Mock()
                            mock_user.id = uuid.uuid4()
                            mock_create.return_value = mock_user
                            
                            result = self.service.create_user(
                                login="testuser",
                                password="password123",
                                role="reader",
                                email="test@example.com"
                            )
                            
                            assert result == mock_user
                            mock_create.assert_called_once()
                            mock_audit.assert_called_once()
    
    def test_create_user_duplicate_login(self):
        """Test user creation with duplicate login"""
        with patch.object(self.service.users_repo, 'get_by_login') as mock_get_login:
            mock_get_login.return_value = Mock()  # User exists
            
            with pytest.raises(ValueError, match="User with this login already exists"):
                self.service.create_user("testuser", "password123")
    
    def test_create_user_duplicate_email(self):
        """Test user creation with duplicate email"""
        with patch.object(self.service.users_repo, 'get_by_login') as mock_get_login:
            with patch.object(self.service.users_repo, 'get_by_email') as mock_get_email:
                mock_get_login.return_value = None
                mock_get_email.return_value = Mock()  # Email exists
                
                with pytest.raises(ValueError, match="User with this email already exists"):
                    self.service.create_user("testuser", "password123", email="test@example.com")
    
    def test_create_user_invalid_password(self):
        """Test user creation with invalid password"""
        with pytest.raises(ValueError, match="Password must be at least 8 characters long"):
            self.service.create_user("testuser", "short")
    
    def test_create_user_invalid_email(self):
        """Test user creation with invalid email"""
        with pytest.raises(ValueError, match="Invalid email format"):
            self.service.create_user("testuser", "password123", email="invalid-email")
    
    def test_authenticate_user_success(self):
        """Test successful user authentication"""
        with patch.object(self.service.users_repo, 'get_by_login') as mock_get_login:
            with patch.object(self.service, '_verify_password') as mock_verify:
                with patch.object(self.service.audit_repo, 'create_log') as mock_audit:
                    mock_user = Mock()
                    mock_user.id = uuid.uuid4()
                    mock_user.is_active = True
                    mock_user.password_hash = "hashed_password"
                    mock_get_login.return_value = mock_user
                    mock_verify.return_value = True
                    
                    result = self.service.authenticate_user("testuser", "password123")
                    
                    assert result == mock_user
                    mock_verify.assert_called_once_with("password123", "hashed_password")
                    mock_audit.assert_called_once()
    
    def test_authenticate_user_invalid_credentials(self):
        """Test user authentication with invalid credentials"""
        with patch.object(self.service.users_repo, 'get_by_login') as mock_get_login:
            with patch.object(self.service, '_verify_password') as mock_verify:
                mock_user = Mock()
                mock_user.is_active = True
                mock_user.password_hash = "hashed_password"
                mock_get_login.return_value = mock_user
                mock_verify.return_value = False
                
                result = self.service.authenticate_user("testuser", "wrongpassword")
                
                assert result is None
    
    def test_authenticate_user_inactive(self):
        """Test user authentication with inactive user"""
        with patch.object(self.service.users_repo, 'get_by_login') as mock_get_login:
            mock_user = Mock()
            mock_user.is_active = False
            mock_get_login.return_value = mock_user
                
            result = self.service.authenticate_user("testuser", "password123")
            
            assert result is None
    
    def test_change_password_success(self):
        """Test successful password change"""
        user_id = str(uuid.uuid4())
        with patch.object(self.service.users_repo, 'get_by_id') as mock_get_user:
            with patch.object(self.service, '_verify_password') as mock_verify:
                with patch.object(self.service, '_hash_password') as mock_hash:
                    with patch.object(self.service.users_repo, 'change_password') as mock_change:
                        with patch.object(self.service.audit_repo, 'create_log') as mock_audit:
                            mock_user = Mock()
                            mock_user.id = user_id
                            mock_user.password_hash = "old_hash"
                            mock_get_user.return_value = mock_user
                            mock_verify.return_value = True
                            mock_hash.return_value = "new_hash"
                            
                            result = self.service.change_password(
                                user_id, "old_password", "new_password"
                            )
                            
                            assert result is True
                            mock_verify.assert_called_once_with("old_password", "old_hash")
                            mock_hash.assert_called_once_with("new_password")
                            mock_change.assert_called_once_with(user_id, "new_hash")
                            mock_audit.assert_called_once()
    
    def test_change_password_invalid_current(self):
        """Test password change with invalid current password"""
        user_id = str(uuid.uuid4())
        with patch.object(self.service.users_repo, 'get_by_id') as mock_get_user:
            with patch.object(self.service, '_verify_password') as mock_verify:
                mock_user = Mock()
                mock_user.id = user_id
                mock_user.password_hash = "old_hash"
                mock_get_user.return_value = mock_user
                mock_verify.return_value = False
                
                with pytest.raises(ValueError, match="Invalid current password"):
                    self.service.change_password(user_id, "wrong_password", "new_password")
    
    def test_create_pat_token_success(self):
        """Test successful PAT token creation"""
        user_id = str(uuid.uuid4())
        with patch.object(self.service.tokens_repo, 'create_token') as mock_create:
            with patch.object(self.service.audit_repo, 'create_log') as mock_audit:
                mock_token = Mock()
                mock_token.id = uuid.uuid4()
                mock_create.return_value = mock_token
                
                result, token = self.service.create_pat_token(
                    user_id, "Test Token", ["read", "write"]
                )
                
                assert result == mock_token
                assert isinstance(token, str)
                mock_create.assert_called_once()
                mock_audit.assert_called_once()
    
    def test_revoke_pat_token_success(self):
        """Test successful PAT token revocation"""
        user_id = str(uuid.uuid4())
        token_id = str(uuid.uuid4())
        with patch.object(self.service.tokens_repo, 'get_by_id') as mock_get_token:
            with patch.object(self.service.tokens_repo, 'revoke_token') as mock_revoke:
                with patch.object(self.service.audit_repo, 'create_log') as mock_audit:
                    mock_token = Mock()
                    mock_token.user_id = user_id
                    mock_get_token.return_value = mock_token
                    mock_revoke.return_value = True
                    
                    result = self.service.revoke_pat_token(user_id, token_id)
                    
                    assert result is True
                    mock_revoke.assert_called_once_with(token_id)
                    mock_audit.assert_called_once()
    
    def test_revoke_pat_token_wrong_owner(self):
        """Test PAT token revocation with wrong owner"""
        user_id = str(uuid.uuid4())
        token_id = str(uuid.uuid4())
        with patch.object(self.service.tokens_repo, 'get_by_id') as mock_get_token:
            mock_token = Mock()
            mock_token.user_id = "other_user"
            mock_get_token.return_value = mock_token
                
            result = self.service.revoke_pat_token(user_id, token_id)
            
            assert result is False


class TestChatsService:
    """Test enhanced chats service"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.service = ChatsService(self.mock_session)
    
    def test_create_chat_success(self):
        """Test successful chat creation"""
        with patch.object(self.service.chats_repo, 'create_chat') as mock_create:
            mock_chat = Mock()
            mock_chat.id = uuid.uuid4()
            mock_create.return_value = mock_chat
            
            result = self.service.create_chat(
                owner_id=str(uuid.uuid4()),
                name="Test Chat",
                tags=["work", "important"]
            )
            
            assert result == mock_chat
            mock_create.assert_called_once()
    
    def test_create_chat_invalid_owner_id(self):
        """Test chat creation with invalid owner ID"""
        with pytest.raises(ValueError, match="Invalid owner ID format"):
            self.service.create_chat("invalid-id", "Test Chat")
    
    def test_create_chat_name_too_long(self):
        """Test chat creation with name too long"""
        with pytest.raises(ValueError, match="Chat name too long"):
            self.service.create_chat(str(uuid.uuid4()), "x" * 201)
    
    def test_create_chat_too_many_tags(self):
        """Test chat creation with too many tags"""
        with pytest.raises(ValueError, match="Too many tags"):
            self.service.create_chat(str(uuid.uuid4()), "Test Chat", ["tag"] * 11)
    
    def test_get_user_chats_success(self):
        """Test successful get user chats"""
        with patch.object(self.service.chats_repo, 'get_user_chats') as mock_get:
            mock_chats = [Mock(), Mock()]
            mock_get.return_value = mock_chats
            
            user_id = str(uuid.uuid4())
            result = self.service.get_user_chats(user_id, "test query", 50)
            
            assert result == mock_chats
            mock_get.assert_called_once_with(user_id, "test query", 50)
    
    def test_get_chat_with_messages_success(self):
        """Test successful get chat with messages"""
        with patch.object(self.service.chats_repo, 'get_chat_with_messages') as mock_get:
            with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_by_id:
                mock_chat = Mock()
                user_id = str(uuid.uuid4())
                mock_chat.owner_id = user_id
                mock_get.return_value = mock_chat
                mock_get_by_id.return_value = mock_chat
                
                chat_id = str(uuid.uuid4())
                result = self.service.get_chat_with_messages(chat_id, user_id)
                
                assert result == mock_chat
                mock_get.assert_called_once_with(chat_id)
    
    def test_get_chat_with_messages_access_denied(self):
        """Test get chat with messages access denied"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_by_id:
            mock_chat = Mock()
            mock_chat.owner_id = str(uuid.uuid4())  # Different user
            mock_get_by_id.return_value = mock_chat
                
            with pytest.raises(ValueError, match="Access denied"):
                self.service.get_chat_with_messages(str(uuid.uuid4()), str(uuid.uuid4()))
    
    def test_update_chat_name_success(self):
        """Test successful chat name update"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_by_id:
            with patch.object(self.service.chats_repo, 'update_chat_name') as mock_update:
                mock_chat = Mock()
                user_id = str(uuid.uuid4())
                mock_chat.owner_id = user_id
                mock_get_by_id.return_value = mock_chat
                mock_updated_chat = Mock()
                mock_update.return_value = mock_updated_chat
                
                chat_id = str(uuid.uuid4())
                result = self.service.update_chat_name(chat_id, user_id, "New Name")
                
                assert result == mock_updated_chat
                mock_update.assert_called_once_with(chat_id, "New Name")
    
    def test_update_chat_name_access_denied(self):
        """Test chat name update access denied"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_by_id:
            mock_chat = Mock()
            mock_chat.owner_id = str(uuid.uuid4())  # Different user
            mock_get_by_id.return_value = mock_chat
                
            with pytest.raises(ValueError, match="Access denied"):
                self.service.update_chat_name(str(uuid.uuid4()), str(uuid.uuid4()), "New Name")
    
    def test_search_chats_success(self):
        """Test successful chat search"""
        with patch.object(self.service.chats_repo, 'search_chats') as mock_search:
            mock_chats = [Mock()]
            mock_search.return_value = mock_chats
            
            user_id = str(uuid.uuid4())
            result = self.service.search_chats(user_id, "test query", 50)
            
            assert result == mock_chats
            mock_search.assert_called_once_with(user_id, "test query", 50)
    
    def test_search_chats_query_too_short(self):
        """Test chat search with query too short"""
        with pytest.raises(ValueError, match="Search query too short"):
            self.service.search_chats(str(uuid.uuid4()), "a", 50)


class TestChatMessagesService:
    """Test enhanced chat messages service"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.service = ChatMessagesService(self.mock_session)
    
    def test_create_message_success(self):
        """Test successful message creation"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_chat:
            with patch.object(self.service.messages_repo, 'create_message') as mock_create:
                mock_chat = Mock()
                user_id = str(uuid.uuid4())
                mock_chat.owner_id = user_id
                mock_get_chat.return_value = mock_chat
                
                mock_message = Mock()
                mock_message.id = uuid.uuid4()
                mock_create.return_value = mock_message
                
                chat_id = str(uuid.uuid4())
                result = self.service.create_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    role="user",
                    content={"text": "Hello world"},
                    model="gpt-4"
                )
                
                assert result == mock_message
                mock_create.assert_called_once()
    
    def test_create_message_invalid_role(self):
        """Test message creation with invalid role"""
        with pytest.raises(ValueError, match="Invalid role"):
            self.service.create_message(
                chat_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
                role="invalid_role",
                content={"text": "Hello world"}
            )
    
    def test_create_message_access_denied(self):
        """Test message creation access denied"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_chat:
            mock_chat = Mock()
            mock_chat.owner_id = str(uuid.uuid4())  # Different user
            mock_get_chat.return_value = mock_chat
                
            with pytest.raises(ValueError, match="Access denied"):
                self.service.create_message(
                    chat_id=str(uuid.uuid4()),
                    user_id=str(uuid.uuid4()),
                    role="user",
                    content={"text": "Hello world"}
                )
    
    def test_get_chat_messages_success(self):
        """Test successful get chat messages"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_chat:
            with patch.object(self.service.messages_repo, 'get_chat_messages') as mock_get:
                mock_chat = Mock()
                user_id = str(uuid.uuid4())
                mock_chat.owner_id = user_id
                mock_get_chat.return_value = mock_chat
                
                mock_messages = [Mock(), Mock()]
                mock_get.return_value = (mock_messages, "next_cursor")
                
                chat_id = str(uuid.uuid4())
                result, next_cursor = self.service.get_chat_messages(
                    chat_id=chat_id,
                    user_id=user_id,
                    limit=50
                )
                
                assert result == mock_messages
                assert next_cursor == "next_cursor"
                mock_get.assert_called_once()
    
    def test_search_messages_success(self):
        """Test successful message search"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_chat:
            with patch.object(self.service.messages_repo, 'search_messages') as mock_search:
                mock_chat = Mock()
                user_id = str(uuid.uuid4())
                mock_chat.owner_id = user_id
                mock_get_chat.return_value = mock_chat
                
                mock_messages = [Mock()]
                mock_search.return_value = mock_messages
                
                chat_id = str(uuid.uuid4())
                result = self.service.search_messages(
                    chat_id=chat_id,
                    user_id=user_id,
                    query="test query"
                )
                
                assert result == mock_messages
                mock_search.assert_called_once_with(chat_id, "test query", 50)
    
    def test_search_messages_query_too_short(self):
        """Test message search with query too short"""
        with patch.object(self.service.chats_repo, 'get_by_id') as mock_get_chat:
            mock_chat = Mock()
            user_id = str(uuid.uuid4())
            mock_chat.owner_id = user_id
            mock_get_chat.return_value = mock_chat
            
            with pytest.raises(ValueError, match="Search query too short"):
                self.service.search_messages(
                    chat_id=str(uuid.uuid4()),
                    user_id=user_id,
                    query="a"
                )


class TestRAGDocumentsService:
    """Test enhanced RAG documents service"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.service = RAGDocumentsService(self.mock_session)
    
    def test_create_document_success(self):
        """Test successful document creation"""
        with patch.object(self.service.documents_repo, 'create_document') as mock_create:
            mock_document = Mock()
            mock_document.id = uuid.uuid4()
            mock_create.return_value = mock_document
            
            user_id = str(uuid.uuid4())
            result = self.service.create_document(
                filename="test.pdf",
                title="Test Document",
                user_id=user_id,
                content_type="application/pdf",
                size=1024,
                tags=["work", "important"]
            )
            
            assert result == mock_document
            mock_create.assert_called_once()
    
    def test_create_document_invalid_user_id(self):
        """Test document creation with invalid user ID"""
        with pytest.raises(ValueError, match="Invalid user ID format"):
            self.service.create_document(
                filename="test.pdf",
                title="Test Document",
                user_id="invalid-id"
            )
    
    def test_create_document_empty_filename(self):
        """Test document creation with empty filename"""
        with pytest.raises(ValueError, match="Filename cannot be empty"):
            self.service.create_document(
                filename="",
                title="Test Document",
                user_id=str(uuid.uuid4())
            )
    
    def test_create_document_unsupported_extension(self):
        """Test document creation with unsupported extension"""
        with pytest.raises(ValueError, match="Unsupported file type"):
            self.service.create_document(
                filename="test.exe",
                title="Test Document",
                user_id=str(uuid.uuid4())
            )
    
    def test_create_document_file_too_large(self):
        """Test document creation with file too large"""
        with pytest.raises(ValueError, match="File too large"):
            self.service.create_document(
                filename="test.pdf",
                title="Test Document",
                user_id=str(uuid.uuid4()),
                size=200 * 1024 * 1024  # 200MB
            )
    
    def test_get_user_documents_success(self):
        """Test successful get user documents"""
        with patch.object(self.service.documents_repo, 'get_user_documents') as mock_get:
            mock_documents = [Mock(), Mock()]
            mock_get.return_value = mock_documents
            
            user_id = str(uuid.uuid4())
            result = self.service.get_user_documents(user_id, "processed", 50, 0)
            
            assert result == mock_documents
            mock_get.assert_called_once_with(user_id=user_id, status="processed", limit=50, offset=0)
    
    def test_get_document_success(self):
        """Test successful get document"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get:
            mock_document = Mock()
            user_id = str(uuid.uuid4())
            mock_document.user_id = user_id
            mock_get.return_value = mock_document
            
            document_id = str(uuid.uuid4())
            result = self.service.get_document(document_id, user_id)
            
            assert result == mock_document
            mock_get.assert_called_once_with(document_id)
    
    def test_get_document_access_denied(self):
        """Test get document access denied"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get:
            mock_document = Mock()
            mock_document.user_id = str(uuid.uuid4())  # Different user
            mock_get.return_value = mock_document
                
            with pytest.raises(ValueError, match="Access denied"):
                self.service.get_document(str(uuid.uuid4()), str(uuid.uuid4()))
    
    def test_search_documents_success(self):
        """Test successful document search"""
        with patch.object(self.service.documents_repo, 'search_documents') as mock_search:
            mock_documents = [Mock()]
            mock_search.return_value = mock_documents
            
            user_id = str(uuid.uuid4())
            result = self.service.search_documents(user_id, "test query", "processed", 50)
            
            assert result == mock_documents
            mock_search.assert_called_once_with(user_id=user_id, query="test query", status="processed", limit=50)
    
    def test_search_documents_query_too_short(self):
        """Test document search with query too short"""
        with pytest.raises(ValueError, match="Search query too short"):
            self.service.search_documents(str(uuid.uuid4()), "a", None, 50)
    
    def test_get_document_stats_success(self):
        """Test successful get document stats"""
        with patch.object(self.service.documents_repo, 'get_document_stats') as mock_stats:
            mock_stats.return_value = {"total": 10, "processed": 8, "processing": 1, "failed": 1}
            
            user_id = str(uuid.uuid4())
            result = self.service.get_document_stats(user_id)
            
            assert result == {"total": 10, "processed": 8, "processing": 1, "failed": 1}
            mock_stats.assert_called_once_with(user_id)


class TestRAGChunksService:
    """Test enhanced RAG chunks service"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_session = Mock()
        self.service = RAGChunksService(self.mock_session)
    
    def test_create_chunk_success(self):
        """Test successful chunk creation"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get_doc:
            with patch.object(self.service.chunks_repo, 'create_chunk') as mock_create:
                mock_document = Mock()
                user_id = str(uuid.uuid4())
                mock_document.user_id = user_id
                mock_get_doc.return_value = mock_document
                
                mock_chunk = Mock()
                mock_chunk.id = uuid.uuid4()
                mock_create.return_value = mock_chunk
                
                document_id = str(uuid.uuid4())
                result = self.service.create_chunk(
                    document_id=document_id,
                    user_id=user_id,
                    content="This is a test chunk",
                    chunk_index=0,
                    embedding=[0.1, 0.2, 0.3]
                )
                
                assert result == mock_chunk
                mock_create.assert_called_once()
    
    def test_create_chunk_access_denied(self):
        """Test chunk creation access denied"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get_doc:
            mock_document = Mock()
            mock_document.user_id = str(uuid.uuid4())  # Different user
            mock_get_doc.return_value = mock_document
                
            with pytest.raises(ValueError, match="Access denied"):
                self.service.create_chunk(
                    document_id=str(uuid.uuid4()),
                    user_id=str(uuid.uuid4()),
                    content="This is a test chunk",
                    chunk_index=0
                )
    
    def test_create_chunk_empty_content(self):
        """Test chunk creation with empty content"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get_doc:
            mock_document = Mock()
            user_id = str(uuid.uuid4())
            mock_document.user_id = user_id
            mock_get_doc.return_value = mock_document
            
            with pytest.raises(ValueError, match="Content cannot be empty"):
                self.service.create_chunk(
                    document_id=str(uuid.uuid4()),
                    user_id=user_id,
                    content="",
                    chunk_index=0
                )
    
    def test_create_chunk_content_too_long(self):
        """Test chunk creation with content too long"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get_doc:
            mock_document = Mock()
            user_id = str(uuid.uuid4())
            mock_document.user_id = user_id
            mock_get_doc.return_value = mock_document
            
            with pytest.raises(ValueError, match="Content too long"):
                self.service.create_chunk(
                    document_id=str(uuid.uuid4()),
                    user_id=user_id,
                    content="x" * 10001,  # Too long
                    chunk_index=0
                )
    
    def test_get_document_chunks_success(self):
        """Test successful get document chunks"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get_doc:
            with patch.object(self.service.chunks_repo, 'get_document_chunks') as mock_get:
                mock_document = Mock()
                user_id = str(uuid.uuid4())
                mock_document.user_id = user_id
                mock_get_doc.return_value = mock_document
                
                mock_chunks = [Mock(), Mock()]
                mock_get.return_value = mock_chunks
                
                document_id = str(uuid.uuid4())
                result = self.service.get_document_chunks(document_id, user_id, 1000)
                
                assert result == mock_chunks
                mock_get.assert_called_once_with(document_id, 1000)
    
    def test_search_chunks_success(self):
        """Test successful chunk search"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get_doc:
            with patch.object(self.service.chunks_repo, 'search_chunks') as mock_search:
                mock_document = Mock()
                user_id = str(uuid.uuid4())
                mock_document.user_id = user_id
                mock_get_doc.return_value = mock_document
                
                mock_chunks = [Mock()]
                mock_search.return_value = mock_chunks
                
                document_id = str(uuid.uuid4())
                result = self.service.search_chunks(document_id, user_id, "test query", 50)
                
                assert result == mock_chunks
                mock_search.assert_called_once_with(document_id, "test query", 50)
    
    def test_search_chunks_query_too_short(self):
        """Test chunk search with query too short"""
        with patch.object(self.service.documents_repo, 'get_by_id') as mock_get_doc:
            mock_document = Mock()
            user_id = str(uuid.uuid4())
            mock_document.user_id = user_id
            mock_get_doc.return_value = mock_document
            
            with pytest.raises(ValueError, match="Search query too short"):
                self.service.search_chunks(str(uuid.uuid4()), user_id, "a", 50)


if __name__ == "__main__":
    pytest.main([__file__])
