"""
Tests for enhanced API controllers
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import uuid
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.api.controllers.users import UsersController
from app.api.controllers.chats import ChatsController, ChatMessagesController
from app.api.controllers.rag import RAGDocumentsController, RAGChunksController
from app.api.schemas.users import UserCreateRequest, UserUpdateRequest, UserSearchRequest
from app.api.schemas.chats import ChatCreateRequest, ChatUpdateRequest, ChatSearchRequest, ChatMessageCreateRequest, ChatMessagesListRequest
from app.api.schemas.rag import RAGDocumentCreateRequest, RAGDocumentUpdateRequest, RAGDocumentSearchRequest, RAGChunkCreateRequest, RAGChunkSearchRequest


class TestUsersController:
    """Test users controller"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_service = Mock()
        self.controller = UsersController(self.mock_service)
        self.current_user = {
            "id": str(uuid.uuid4()),
            "login": "testuser",
            "role": "admin"
        }
    
    @pytest.mark.asyncio
    async def test_create_user_success(self):
        """Test successful user creation"""
        request = UserCreateRequest(
            login="newuser",
            password="Password123",
            email="newuser@example.com",
            role="reader"
        )
        
        mock_user = Mock()
        mock_user.id = str(uuid.uuid4())
        mock_user.login = "newuser"
        mock_user.email = "newuser@example.com"
        mock_user.role = "reader"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'create_user') as mock_create:
            mock_create.return_value = mock_user
            
            result = await self.controller.create_user(request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["login"] == "newuser"
            assert result["data"]["email"] == "newuser@example.com"
            assert result["data"]["role"] == "reader"
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_user_non_admin(self):
        """Test user creation with non-admin user"""
        request = UserCreateRequest(
            login="newuser",
            password="Password123"
        )
        
        non_admin_user = {
            "id": str(uuid.uuid4()),
            "login": "testuser",
            "role": "reader"
        }
        
        with pytest.raises(Exception):  # Should raise PermissionError
            await self.controller.create_user(request, non_admin_user)
    
    @pytest.mark.asyncio
    async def test_get_user_success(self):
        """Test successful user retrieval"""
        user_id = str(uuid.uuid4())
        
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.login = "testuser"
        mock_user.email = "testuser@example.com"
        mock_user.role = "reader"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'get_by_id') as mock_get:
            mock_get.return_value = mock_user
            
            result = await self.controller.get_user(user_id, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["id"] == user_id
            mock_get.assert_called_once_with(user_id)
    
    @pytest.mark.asyncio
    async def test_get_user_not_found(self):
        """Test user retrieval when user not found"""
        user_id = str(uuid.uuid4())
        
        with patch.object(self.controller.service, 'get_by_id') as mock_get:
            mock_get.return_value = None
            
            with pytest.raises(Exception):  # Should raise HTTPException
                await self.controller.get_user(user_id, self.current_user)
    
    @pytest.mark.asyncio
    async def test_update_user_success(self):
        """Test successful user update"""
        user_id = str(uuid.uuid4())
        request = UserUpdateRequest(
            email="updated@example.com",
            role="editor"
        )
        
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.login = "testuser"
        mock_user.email = "updated@example.com"
        mock_user.role = "editor"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.updated_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'update') as mock_update:
            mock_update.return_value = mock_user
            
            result = await self.controller.update_user(user_id, request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["email"] == "updated@example.com"
            assert result["data"]["role"] == "editor"
            mock_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_users_success(self):
        """Test successful user search"""
        request = UserSearchRequest(
            query="test",
            role="reader",
            limit=10,
            offset=0
        )
        
        mock_users = [Mock(), Mock()]
        for i, user in enumerate(mock_users):
            user.id = str(uuid.uuid4())
            user.login = f"user{i}"
            user.email = f"user{i}@example.com"
            user.role = "reader"
            user.is_active = True
            user.created_at = datetime.now(timezone.utc)
            user.updated_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'search_users') as mock_search:
            with patch.object(self.controller.service, 'count') as mock_count:
                mock_search.return_value = mock_users
                mock_count.return_value = 2
                
                result = await self.controller.search_users(request, self.current_user)
                
                assert result["success"] is True
                assert "data" in result
                assert len(result["data"]["users"]) == 2
                mock_search.assert_called_once()


class TestChatsController:
    """Test chats controller"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_service = Mock()
        self.controller = ChatsController(self.mock_service)
        self.current_user = {
            "id": str(uuid.uuid4()),
            "login": "testuser",
            "role": "reader"
        }
    
    @pytest.mark.asyncio
    async def test_create_chat_success(self):
        """Test successful chat creation"""
        request = ChatCreateRequest(
            name="Test Chat",
            tags=["work", "important"]
        )
        
        mock_chat = Mock()
        mock_chat.id = str(uuid.uuid4())
        mock_chat.name = "Test Chat"
        mock_chat.tags = ["work", "important"]
        mock_chat.owner_id = self.current_user["id"]
        mock_chat.created_at = datetime.now(timezone.utc)
        mock_chat.updated_at = datetime.now(timezone.utc)
        mock_chat.last_message_at = None
        
        with patch.object(self.controller.service, 'create_chat') as mock_create:
            mock_create.return_value = mock_chat
            
            result = await self.controller.create_chat(request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["name"] == "Test Chat"
            assert result["data"]["tags"] == ["work", "important"]
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_chat_success(self):
        """Test successful chat retrieval"""
        chat_id = str(uuid.uuid4())
        
        mock_chat = Mock()
        mock_chat.id = chat_id
        mock_chat.name = "Test Chat"
        mock_chat.tags = ["work"]
        mock_chat.owner_id = self.current_user["id"]
        mock_chat.created_at = datetime.now(timezone.utc)
        mock_chat.updated_at = datetime.now(timezone.utc)
        mock_chat.last_message_at = None
        
        with patch.object(self.controller.service, 'get_chat_with_messages') as mock_get:
            mock_get.return_value = mock_chat
            
            result = await self.controller.get_chat(chat_id, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["id"] == chat_id
            mock_get.assert_called_once_with(chat_id, self.current_user["id"])
    
    @pytest.mark.asyncio
    async def test_get_chat_not_found(self):
        """Test chat retrieval when chat not found"""
        chat_id = str(uuid.uuid4())
        
        with patch.object(self.controller.service, 'get_chat_with_messages') as mock_get:
            mock_get.return_value = None
            
            with pytest.raises(Exception):  # Should raise HTTPException
                await self.controller.get_chat(chat_id, self.current_user)
    
    @pytest.mark.asyncio
    async def test_update_chat_success(self):
        """Test successful chat update"""
        chat_id = str(uuid.uuid4())
        request = ChatUpdateRequest(
            name="Updated Chat",
            tags=["updated"]
        )
        
        mock_chat = Mock()
        mock_chat.id = chat_id
        mock_chat.name = "Updated Chat"
        mock_chat.tags = ["updated"]
        mock_chat.owner_id = self.current_user["id"]
        mock_chat.created_at = datetime.now(timezone.utc)
        mock_chat.updated_at = datetime.now(timezone.utc)
        mock_chat.last_message_at = None
        
        with patch.object(self.controller.service, 'update_chat_name') as mock_update_name:
            with patch.object(self.controller.service, 'update_chat_tags') as mock_update_tags:
                with patch.object(self.controller.service, 'get_chat_with_messages') as mock_get:
                    mock_update_name.return_value = mock_chat
                    mock_update_tags.return_value = mock_chat
                    mock_get.return_value = mock_chat
                    
                    result = await self.controller.update_chat(chat_id, request, self.current_user)
                    
                    assert result["success"] is True
                    assert "data" in result
                    assert result["data"]["name"] == "Updated Chat"
                    assert result["data"]["tags"] == ["updated"]
    
    @pytest.mark.asyncio
    async def test_get_user_chats_success(self):
        """Test successful user chats retrieval"""
        request = ChatSearchRequest(
            query="test",
            limit=10,
            offset=0
        )
        
        mock_chats = [Mock(), Mock()]
        for i, chat in enumerate(mock_chats):
            chat.id = str(uuid.uuid4())
            chat.name = f"Chat {i}"
            chat.tags = ["work"]
            chat.owner_id = self.current_user["id"]
            chat.created_at = datetime.now(timezone.utc)
            chat.updated_at = datetime.now(timezone.utc)
            chat.last_message_at = None
        
        with patch.object(self.controller.service, 'search_chats') as mock_search:
            mock_search.return_value = mock_chats
            
            result = await self.controller.get_user_chats(request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert len(result["data"]["chats"]) == 2
            mock_search.assert_called_once()


class TestChatMessagesController:
    """Test chat messages controller"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_service = Mock()
        self.controller = ChatMessagesController(self.mock_service)
        self.current_user = {
            "id": str(uuid.uuid4()),
            "login": "testuser",
            "role": "reader"
        }
    
    @pytest.mark.asyncio
    async def test_create_message_success(self):
        """Test successful message creation"""
        chat_id = str(uuid.uuid4())
        request = ChatMessageCreateRequest(
            role="user",
            content={"text": "Hello world"},
            model="gpt-4"
        )
        
        mock_message = Mock()
        mock_message.id = str(uuid.uuid4())
        mock_message.chat_id = chat_id
        mock_message.role = "user"
        mock_message.content = {"text": "Hello world"}
        mock_message.model = "gpt-4"
        mock_message.tokens_in = None
        mock_message.tokens_out = None
        mock_message.meta = None
        mock_message.created_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'create_message') as mock_create:
            mock_create.return_value = mock_message
            
            result = await self.controller.create_message(chat_id, request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["role"] == "user"
            assert result["data"]["content"] == {"text": "Hello world"}
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_chat_messages_success(self):
        """Test successful chat messages retrieval"""
        chat_id = str(uuid.uuid4())
        request = ChatMessagesListRequest(
            limit=10,
            cursor=None,
            role=None
        )
        
        mock_messages = [Mock(), Mock()]
        for i, message in enumerate(mock_messages):
            message.id = str(uuid.uuid4())
            message.chat_id = chat_id
            message.role = "user" if i % 2 == 0 else "assistant"
            message.content = {"text": f"Message {i}"}
            message.model = "gpt-4"
            message.tokens_in = None
            message.tokens_out = None
            message.meta = None
            message.created_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'get_chat_messages') as mock_get:
            mock_get.return_value = (mock_messages, "next_cursor")
            
            result = await self.controller.get_chat_messages(chat_id, request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert len(result["data"]["messages"]) == 2
            assert result["data"]["cursor"] == "next_cursor"
            mock_get.assert_called_once()


class TestRAGDocumentsController:
    """Test RAG documents controller"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_service = Mock()
        self.controller = RAGDocumentsController(self.mock_service)
        self.current_user = {
            "id": str(uuid.uuid4()),
            "login": "testuser",
            "role": "reader"
        }
    
    @pytest.mark.asyncio
    async def test_create_document_success(self):
        """Test successful document creation"""
        request = RAGDocumentCreateRequest(
            filename="test.pdf",
            title="Test Document",
            content_type="application/pdf",
            size=1024,
            tags=["work", "important"]
        )
        
        mock_document = Mock()
        mock_document.id = str(uuid.uuid4())
        mock_document.filename = "test.pdf"
        mock_document.title = "Test Document"
        mock_document.content_type = "application/pdf"
        mock_document.size = 1024
        mock_document.tags = ["work", "important"]
        mock_document.status = "uploading"
        mock_document.error_message = None
        mock_document.s3_key_raw = None
        mock_document.s3_key_processed = None
        mock_document.user_id = self.current_user["id"]
        mock_document.created_at = datetime.now(timezone.utc)
        mock_document.updated_at = datetime.now(timezone.utc)
        mock_document.processed_at = None
        
        with patch.object(self.controller.service, 'create_document') as mock_create:
            mock_create.return_value = mock_document
            
            result = await self.controller.create_document(request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["filename"] == "test.pdf"
            assert result["data"]["title"] == "Test Document"
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_document_success(self):
        """Test successful document retrieval"""
        document_id = str(uuid.uuid4())
        
        mock_document = Mock()
        mock_document.id = document_id
        mock_document.filename = "test.pdf"
        mock_document.title = "Test Document"
        mock_document.content_type = "application/pdf"
        mock_document.size = 1024
        mock_document.tags = ["work"]
        mock_document.status = "processed"
        mock_document.error_message = None
        mock_document.s3_key_raw = "test.pdf"
        mock_document.s3_key_processed = "processed.pdf"
        mock_document.user_id = self.current_user["id"]
        mock_document.created_at = datetime.now(timezone.utc)
        mock_document.updated_at = datetime.now(timezone.utc)
        mock_document.processed_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'get_document') as mock_get:
            mock_get.return_value = mock_document
            
            result = await self.controller.get_document(document_id, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["id"] == document_id
            mock_get.assert_called_once_with(document_id, self.current_user["id"])
    
    @pytest.mark.asyncio
    async def test_get_document_not_found(self):
        """Test document retrieval when document not found"""
        document_id = str(uuid.uuid4())
        
        with patch.object(self.controller.service, 'get_document') as mock_get:
            mock_get.return_value = None
            
            with pytest.raises(Exception):  # Should raise HTTPException
                await self.controller.get_document(document_id, self.current_user)
    
    @pytest.mark.asyncio
    async def test_search_documents_success(self):
        """Test successful document search"""
        request = RAGDocumentSearchRequest(
            query="test",
            status="processed",
            limit=10,
            offset=0
        )
        
        mock_documents = [Mock(), Mock()]
        for i, doc in enumerate(mock_documents):
            doc.id = str(uuid.uuid4())
            doc.filename = f"test{i}.pdf"
            doc.title = f"Test Document {i}"
            doc.content_type = "application/pdf"
            doc.size = 1024
            doc.tags = ["work"]
            doc.status = "processed"
            doc.error_message = None
            doc.s3_key_raw = f"test{i}.pdf"
            doc.s3_key_processed = f"processed{i}.pdf"
            doc.user_id = self.current_user["id"]
            doc.created_at = datetime.now(timezone.utc)
            doc.updated_at = datetime.now(timezone.utc)
            doc.processed_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'search_documents') as mock_search:
            mock_search.return_value = mock_documents
            
            result = await self.controller.search_documents(request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert len(result["data"]["documents"]) == 2
            mock_search.assert_called_once()


class TestRAGChunksController:
    """Test RAG chunks controller"""
    
    def setup_method(self):
        """Setup test method"""
        self.mock_service = Mock()
        self.controller = RAGChunksController(self.mock_service)
        self.current_user = {
            "id": str(uuid.uuid4()),
            "login": "testuser",
            "role": "reader"
        }
    
    @pytest.mark.asyncio
    async def test_create_chunk_success(self):
        """Test successful chunk creation"""
        document_id = str(uuid.uuid4())
        request = RAGChunkCreateRequest(
            content="This is a test chunk",
            chunk_index=0,
            embedding=[0.1, 0.2, 0.3],
            vector_id="vec123",
            chunk_metadata={"source": "test"}
        )
        
        mock_chunk = Mock()
        mock_chunk.id = str(uuid.uuid4())
        mock_chunk.document_id = document_id
        mock_chunk.content = "This is a test chunk"
        mock_chunk.chunk_index = 0
        mock_chunk.embedding = [0.1, 0.2, 0.3]
        mock_chunk.vector_id = "vec123"
        mock_chunk.chunk_metadata = {"source": "test"}
        mock_chunk.created_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'create_chunk') as mock_create:
            mock_create.return_value = mock_chunk
            
            result = await self.controller.create_chunk(document_id, request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["content"] == "This is a test chunk"
            assert result["data"]["chunk_index"] == 0
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_document_chunks_success(self):
        """Test successful document chunks retrieval"""
        document_id = str(uuid.uuid4())
        limit = 10
        
        mock_chunks = [Mock(), Mock()]
        for i, chunk in enumerate(mock_chunks):
            chunk.id = str(uuid.uuid4())
            chunk.document_id = document_id
            chunk.content = f"Chunk {i}"
            chunk.chunk_index = i
            chunk.embedding = [0.1, 0.2, 0.3]
            chunk.vector_id = f"vec{i}"
            chunk.chunk_metadata = {}
            chunk.created_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'get_document_chunks') as mock_get:
            mock_get.return_value = mock_chunks
            
            result = await self.controller.get_document_chunks(document_id, limit, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert len(result["data"]["chunks"]) == 2
            mock_get.assert_called_once_with(document_id, self.current_user["id"], limit)
    
    @pytest.mark.asyncio
    async def test_search_chunks_success(self):
        """Test successful chunk search"""
        document_id = str(uuid.uuid4())
        request = RAGChunkSearchRequest(
            query="test",
            limit=10,
            offset=0
        )
        
        mock_chunks = [Mock(), Mock()]
        for i, chunk in enumerate(mock_chunks):
            chunk.id = str(uuid.uuid4())
            chunk.document_id = document_id
            chunk.content = f"Test chunk {i}"
            chunk.chunk_index = i
            chunk.embedding = [0.1, 0.2, 0.3]
            chunk.vector_id = f"vec{i}"
            chunk.chunk_metadata = {}
            chunk.created_at = datetime.now(timezone.utc)
        
        with patch.object(self.controller.service, 'search_chunks') as mock_search:
            mock_search.return_value = mock_chunks
            
            result = await self.controller.search_chunks(document_id, request, self.current_user)
            
            assert result["success"] is True
            assert "data" in result
            assert len(result["data"]["chunks"]) == 2
            mock_search.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
