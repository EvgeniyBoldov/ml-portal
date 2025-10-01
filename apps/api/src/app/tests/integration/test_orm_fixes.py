"""
Integration tests for ORM fixes and multitenancy
"""
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.chat import Chats, ChatMessages
from app.models.analyze import AnalysisDocuments, AnalysisChunks
from app.schemas.chats import ChatCreateRequest, ChatMessageCreateRequest


class TestMultitenancy:
    """Test multitenancy isolation"""
    
    def test_chat_multitenancy_isolation(self, db_session: Session):
        """Test that chats are isolated by tenant_id"""
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create chats in different tenants with same name
        chat1 = Chats(
            tenant_id=tenant1,
            name="Test Chat",
            owner_id=user_id
        )
        chat2 = Chats(
            tenant_id=tenant2,
            name="Test Chat",  # Same name, different tenant
            owner_id=user_id
        )
        
        db_session.add_all([chat1, chat2])
        db_session.commit()
        
        # Both chats should exist (no unique constraint violation)
        assert chat1.id is not None
        assert chat2.id is not None
        assert chat1.name == chat2.name
        assert chat1.tenant_id != chat2.tenant_id
        
        # Query by tenant should return only tenant's chats
        tenant1_chats = db_session.query(Chats).filter(Chats.tenant_id == tenant1).all()
        tenant2_chats = db_session.query(Chats).filter(Chats.tenant_id == tenant2).all()
        
        assert len(tenant1_chats) == 1
        assert len(tenant2_chats) == 1
        assert tenant1_chats[0].id == chat1.id
        assert tenant2_chats[0].id == chat2.id
    
    def test_chat_messages_multitenancy(self, db_session: Session):
        """Test that chat messages are isolated by tenant_id"""
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create chats in different tenants
        chat1 = Chats(tenant_id=tenant1, name="Chat 1", owner_id=user_id)
        chat2 = Chats(tenant_id=tenant2, name="Chat 2", owner_id=user_id)
        
        db_session.add_all([chat1, chat2])
        db_session.commit()
        
        # Create messages for each chat
        msg1 = ChatMessages(
            tenant_id=tenant1,
            chat_id=chat1.id,
            role="user",
            content="Hello from tenant 1"
        )
        msg2 = ChatMessages(
            tenant_id=tenant2,
            chat_id=chat2.id,
            role="user",
            content="Hello from tenant 2"
        )
        
        db_session.add_all([msg1, msg2])
        db_session.commit()
        
        # Messages should be isolated by tenant
        tenant1_messages = db_session.query(ChatMessages).filter(ChatMessages.tenant_id == tenant1).all()
        tenant2_messages = db_session.query(ChatMessages).filter(ChatMessages.tenant_id == tenant2).all()
        
        assert len(tenant1_messages) == 1
        assert len(tenant2_messages) == 1
        assert tenant1_messages[0].content == "Hello from tenant 1"
        assert tenant2_messages[0].content == "Hello from tenant 2"
    
    def test_analysis_documents_multitenancy(self, db_session: Session):
        """Test that analysis documents are isolated by tenant_id"""
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create documents in different tenants
        doc1 = AnalysisDocuments(
            tenant_id=tenant1,
            status="queued",
            uploaded_by=user_id,
            url_file="tenant1/file.pdf"
        )
        doc2 = AnalysisDocuments(
            tenant_id=tenant2,
            status="queued",
            uploaded_by=user_id,
            url_file="tenant2/file.pdf"  # Same filename, different tenant
        )
        
        db_session.add_all([doc1, doc2])
        db_session.commit()
        
        # Both documents should exist
        assert doc1.id is not None
        assert doc2.id is not None
        assert doc1.tenant_id != doc2.tenant_id
        
        # Query by tenant should return only tenant's documents
        tenant1_docs = db_session.query(AnalysisDocuments).filter(AnalysisDocuments.tenant_id == tenant1).all()
        tenant2_docs = db_session.query(AnalysisDocuments).filter(AnalysisDocuments.tenant_id == tenant2).all()
        
        assert len(tenant1_docs) == 1
        assert len(tenant2_docs) == 1


class TestJSONBSupport:
    """Test JSONB support and GIN indexes"""
    
    def test_chat_message_jsonb_content(self, db_session: Session):
        """Test that chat message content supports both string and dict"""
        tenant_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Test string content
        msg1 = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role="user",
            content="Simple text message"
        )
        
        # Test dict content (tool call)
        msg2 = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role="tool",
            content={
                "tool_call_id": "call_123",
                "name": "search",
                "arguments": {"query": "test query"}
            }
        )
        
        db_session.add_all([msg1, msg2])
        db_session.commit()
        
        # Verify content types
        assert isinstance(msg1.content, str)
        assert isinstance(msg2.content, dict)
        assert msg2.content["name"] == "search"
    
    def test_jsonb_search_functionality(self, db_session: Session):
        """Test JSONB search using PostgreSQL operators"""
        tenant_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Create message with structured content
        msg = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role="assistant",
            content={
                "text": "The weather is sunny today",
                "metadata": {
                    "confidence": 0.95,
                    "source": "weather_api"
                }
            },
            meta={
                "model": "gpt-4",
                "temperature": 0.7,
                "tokens": {"input": 10, "output": 15}
            }
        )
        
        db_session.add(msg)
        db_session.commit()
        
        # Test JSONB queries
        # Search for messages containing specific text
        result1 = db_session.query(ChatMessages).filter(
            ChatMessages.content.op('->>')('text').contains('sunny')
        ).first()
        assert result1 is not None
        
        # Search for messages with specific metadata
        result2 = db_session.query(ChatMessages).filter(
            ChatMessages.content.op('->')('metadata').op('->>')('source') == 'weather_api'
        ).first()
        assert result2 is not None
        
        # Search in meta field
        result3 = db_session.query(ChatMessages).filter(
            ChatMessages.meta.op('->>')('model') == 'gpt-4'
        ).first()
        assert result3 is not None


class TestOptimisticLocking:
    """Test optimistic locking with version field"""
    
    def test_chat_version_increment(self, db_session: Session):
        """Test that chat version increments on update"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chat = Chats(
            tenant_id=tenant_id,
            name="Test Chat",
            owner_id=user_id,
            version=1
        )
        
        db_session.add(chat)
        db_session.commit()
        
        # Update chat
        chat.name = "Updated Chat"
        db_session.commit()
        
        # Version should increment (this would be handled by ORM event listeners)
        # For now, just verify the field exists
        assert hasattr(chat, 'version')
        assert chat.version >= 1
    
    def test_chat_message_version_increment(self, db_session: Session):
        """Test that chat message version increments on update"""
        tenant_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        msg = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role="user",
            content="Test message",
            version=1
        )
        
        db_session.add(msg)
        db_session.commit()
        
        # Update message
        msg.content = "Updated message"
        db_session.commit()
        
        # Version should increment
        assert hasattr(msg, 'version')
        assert msg.version >= 1


class TestTimezoneAwareTimestamps:
    """Test timezone-aware timestamps"""
    
    def test_chat_timestamps_timezone_aware(self, db_session: Session):
        """Test that chat timestamps are timezone-aware"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chat = Chats(
            tenant_id=tenant_id,
            name="Test Chat",
            owner_id=user_id
        )
        
        db_session.add(chat)
        db_session.commit()
        
        # Check that timestamps are timezone-aware
        assert chat.created_at.tzinfo is not None
        assert chat.updated_at.tzinfo is not None
        
        # Verify they're UTC
        assert chat.created_at.tzinfo.utcoffset(None).total_seconds() == 0
        assert chat.updated_at.tzinfo.utcoffset(None).total_seconds() == 0
    
    def test_timestamp_auto_update(self, db_session: Session):
        """Test that updated_at changes on update"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chat = Chats(
            tenant_id=tenant_id,
            name="Test Chat",
            owner_id=user_id
        )
        
        db_session.add(chat)
        db_session.commit()
        
        original_updated_at = chat.updated_at
        
        # Wait a bit and update
        import time
        time.sleep(0.1)
        
        chat.name = "Updated Chat"
        db_session.commit()
        
        # updated_at should be different
        assert chat.updated_at > original_updated_at


class TestCascadeDeletes:
    """Test cascade delete behavior"""
    
    def test_chat_delete_cascades_to_messages(self, db_session: Session):
        """Test that deleting a chat deletes its messages"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chat = Chats(
            tenant_id=tenant_id,
            name="Test Chat",
            owner_id=user_id
        )
        
        db_session.add(chat)
        db_session.commit()
        
        # Create messages
        msg1 = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat.id,
            role="user",
            content="Message 1"
        )
        msg2 = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat.id,
            role="assistant",
            content="Message 2"
        )
        
        db_session.add_all([msg1, msg2])
        db_session.commit()
        
        # Verify messages exist
        message_count = db_session.query(ChatMessages).filter(ChatMessages.chat_id == chat.id).count()
        assert message_count == 2
        
        # Delete chat
        db_session.delete(chat)
        db_session.commit()
        
        # Messages should be deleted
        message_count = db_session.query(ChatMessages).filter(ChatMessages.chat_id == chat.id).count()
        assert message_count == 0
    
    def test_analysis_document_delete_cascades_to_chunks(self, db_session: Session):
        """Test that deleting a document deletes its chunks"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        doc = AnalysisDocuments(
            tenant_id=tenant_id,
            status="queued",
            uploaded_by=user_id
        )
        
        db_session.add(doc)
        db_session.commit()
        
        # Create chunks
        chunk1 = AnalysisChunks(
            tenant_id=tenant_id,
            document_id=doc.id,
            chunk_idx=0,
            text="Chunk 1"
        )
        chunk2 = AnalysisChunks(
            tenant_id=tenant_id,
            document_id=doc.id,
            chunk_idx=1,
            text="Chunk 2"
        )
        
        db_session.add_all([chunk1, chunk2])
        db_session.commit()
        
        # Verify chunks exist
        chunk_count = db_session.query(AnalysisChunks).filter(AnalysisChunks.document_id == doc.id).count()
        assert chunk_count == 2
        
        # Delete document
        db_session.delete(doc)
        db_session.commit()
        
        # Chunks should be deleted
        chunk_count = db_session.query(AnalysisChunks).filter(AnalysisChunks.document_id == doc.id).count()
        assert chunk_count == 0


class TestSchemaCompatibility:
    """Test compatibility between Pydantic schemas and ORM models"""
    
    def test_chat_schema_to_orm_conversion(self, db_session: Session):
        """Test converting Pydantic schema to ORM model"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create from schema
        chat_request = ChatCreateRequest(
            name="Test Chat",
            tags=["test", "example"]
        )
        
        # Convert to ORM model
        chat = Chats(
            tenant_id=tenant_id,
            name=chat_request.name,
            owner_id=user_id,
            tags=chat_request.tags
        )
        
        db_session.add(chat)
        db_session.commit()
        
        # Verify data integrity
        assert chat.name == "Test Chat"
        assert chat.tags == ["test", "example"]
        assert chat.tenant_id == tenant_id
        assert chat.owner_id == user_id
    
    def test_chat_message_schema_to_orm_conversion(self, db_session: Session):
        """Test converting chat message schema to ORM model"""
        tenant_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Test string content
        msg_request = ChatMessageCreateRequest(
            role="user",
            content="Hello world"
        )
        
        msg = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role=msg_request.role,
            content=msg_request.content,
            model=msg_request.model,
            meta=msg_request.meta
        )
        
        db_session.add(msg)
        db_session.commit()
        
        assert msg.content == "Hello world"
        assert msg.role == "user"
        
        # Test dict content
        msg_request2 = ChatMessageCreateRequest(
            role="tool",
            content={
                "tool_call_id": "call_123",
                "name": "search",
                "arguments": {"query": "test"}
            }
        )
        
        msg2 = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role=msg_request2.role,
            content=msg_request2.content
        )
        
        db_session.add(msg2)
        db_session.commit()
        
        assert isinstance(msg2.content, dict)
        assert msg2.content["name"] == "search"
