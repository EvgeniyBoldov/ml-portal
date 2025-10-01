"""
Integration tests for critical migration fixes
"""
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.chat import Chats, ChatMessages
from app.models.analyze import AnalysisDocuments, AnalysisChunks
from app.schemas.chats import ChatCreateRequest, ChatMessageCreateRequest


class TestUpdatedAtTriggers:
    """Test that updated_at triggers work for all tables"""
    
    def test_chats_updated_at_trigger(self, db_session: Session):
        """Test that chats updated_at trigger works"""
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
        
        # updated_at should be different (trigger should have fired)
        assert chat.updated_at > original_updated_at
    
    def test_chatmessages_updated_at_trigger(self, db_session: Session):
        """Test that chatmessages updated_at trigger works"""
        tenant_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        msg = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role="user",
            content="Test message"
        )
        
        db_session.add(msg)
        db_session.commit()
        
        original_updated_at = msg.updated_at
        
        # Wait a bit and update
        import time
        time.sleep(0.1)
        
        msg.content = "Updated message"
        db_session.commit()
        
        # updated_at should be different (trigger should have fired)
        assert msg.updated_at > original_updated_at
    
    def test_analysisdocuments_updated_at_trigger(self, db_session: Session):
        """Test that analysisdocuments updated_at trigger works"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        doc = AnalysisDocuments(
            tenant_id=tenant_id,
            status="queued",
            uploaded_by=user_id
        )
        
        db_session.add(doc)
        db_session.commit()
        
        original_updated_at = doc.updated_at
        
        # Wait a bit and update
        import time
        time.sleep(0.1)
        
        doc.status = "processing"
        db_session.commit()
        
        # updated_at should be different (trigger should have fired)
        assert doc.updated_at > original_updated_at
    
    def test_analysischunks_updated_at_trigger(self, db_session: Session):
        """Test that analysischunks updated_at trigger works"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        doc = AnalysisDocuments(
            tenant_id=tenant_id,
            status="queued",
            uploaded_by=user_id
        )
        db_session.add(doc)
        db_session.commit()
        
        chunk = AnalysisChunks(
            tenant_id=tenant_id,
            document_id=doc.id,
            chunk_idx=0,
            text="Test chunk"
        )
        
        db_session.add(chunk)
        db_session.commit()
        
        original_updated_at = chunk.updated_at
        
        # Wait a bit and update
        import time
        time.sleep(0.1)
        
        chunk.text = "Updated chunk"
        db_session.commit()
        
        # updated_at should be different (trigger should have fired)
        assert chunk.updated_at > original_updated_at


class TestTimezoneHandling:
    """Test timezone handling in timestamps"""
    
    def test_timestamps_are_timezone_aware(self, db_session: Session):
        """Test that all timestamps are timezone-aware"""
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
    
    def test_server_default_timestamps(self, db_session: Session):
        """Test that server default timestamps work correctly"""
        tenant_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Insert without specifying timestamps
        msg = ChatMessages(
            tenant_id=tenant_id,
            chat_id=chat_id,
            role="user",
            content="Test message"
        )
        
        db_session.add(msg)
        db_session.commit()
        
        # Timestamps should be set by server
        assert msg.created_at is not None
        assert msg.updated_at is not None
        assert msg.created_at.tzinfo is not None
        assert msg.updated_at.tzinfo is not None


class TestUniqueConstraintsWithNulls:
    """Test unique constraints with NULL values"""
    
    def test_analysisdocuments_url_file_null_handling(self, db_session: Session):
        """Test that multiple NULL url_file values are allowed"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create multiple documents with NULL url_file
        doc1 = AnalysisDocuments(
            tenant_id=tenant_id,
            status="queued",
            uploaded_by=user_id,
            url_file=None
        )
        doc2 = AnalysisDocuments(
            tenant_id=tenant_id,
            status="queued",
            uploaded_by=user_id,
            url_file=None  # Same tenant, NULL url_file
        )
        
        db_session.add_all([doc1, doc2])
        db_session.commit()
        
        # Both should be created successfully
        assert doc1.id is not None
        assert doc2.id is not None
    
    def test_analysisdocuments_url_file_unique_non_null(self, db_session: Session):
        """Test that non-NULL url_file values are unique per tenant"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create document with specific url_file
        doc1 = AnalysisDocuments(
            tenant_id=tenant_id,
            status="queued",
            uploaded_by=user_id,
            url_file="test.pdf"
        )
        db_session.add(doc1)
        db_session.commit()
        
        # Try to create another document with same url_file in same tenant
        doc2 = AnalysisDocuments(
            tenant_id=tenant_id,
            status="queued",
            uploaded_by=user_id,
            url_file="test.pdf"  # Same tenant, same url_file
        )
        db_session.add(doc2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_analysisdocuments_url_file_unique_different_tenants(self, db_session: Session):
        """Test that same url_file is allowed in different tenants"""
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create documents with same url_file in different tenants
        doc1 = AnalysisDocuments(
            tenant_id=tenant1,
            status="queued",
            uploaded_by=user_id,
            url_file="test.pdf"
        )
        doc2 = AnalysisDocuments(
            tenant_id=tenant2,
            status="queued",
            uploaded_by=user_id,
            url_file="test.pdf"  # Same url_file, different tenant
        )
        
        db_session.add_all([doc1, doc2])
        db_session.commit()
        
        # Both should be created successfully
        assert doc1.id is not None
        assert doc2.id is not None


class TestEnumCompatibility:
    """Test ENUM compatibility between DB and Pydantic"""
    
    def test_chat_role_enum_all_values(self, db_session: Session):
        """Test that all ENUM values work in database"""
        tenant_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Test all ENUM values
        valid_roles = ['system', 'user', 'assistant', 'tool']
        
        for role in valid_roles:
            msg = ChatMessages(
                tenant_id=tenant_id,
                chat_id=chat_id,
                role=role,
                content=f"Test message with role {role}"
            )
            db_session.add(msg)
            db_session.commit()
            
            # Verify the role was saved correctly
            saved_msg = db_session.query(ChatMessages).filter(ChatMessages.role == role).first()
            assert saved_msg is not None
            assert saved_msg.role == role
            
            db_session.delete(saved_msg)
            db_session.commit()
    
    def test_pydantic_schema_enum_compatibility(self):
        """Test that Pydantic schemas support all ENUM values"""
        from pydantic import ValidationError
        
        # Test all ENUM values in Pydantic
        valid_roles = ['system', 'user', 'assistant', 'tool']
        
        for role in valid_roles:
            msg_request = ChatMessageCreateRequest(
                role=role,
                content=f"Test message with role {role}"
            )
            assert msg_request.role == role
        
        # Test invalid role
        with pytest.raises(ValidationError):
            ChatMessageCreateRequest(
                role="invalid_role",
                content="Test message"
            )


class TestForeignKeyCascades:
    """Test foreign key cascade behavior"""
    
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


class TestMigrationStructure:
    """Test migration structure and integrity"""
    
    def test_all_tables_have_required_columns(self, db_engine):
        """Test that all tables have required columns"""
        from sqlalchemy import inspect
        
        inspector = inspect(db_engine)
        
        # Check chats table
        chats_columns = inspector.get_columns('chats')
        column_names = [col['name'] for col in chats_columns]
        assert 'updated_at' in column_names
        assert 'created_at' in column_names
        assert 'version' in column_names
        assert 'tenant_id' in column_names
        
        # Check chatmessages table
        messages_columns = inspector.get_columns('chatmessages')
        message_column_names = [col['name'] for col in messages_columns]
        assert 'updated_at' in message_column_names
        assert 'created_at' in message_column_names
        assert 'version' in message_column_names
        assert 'tenant_id' in message_column_names
        
        # Check analysisdocuments table
        docs_columns = inspector.get_columns('analysisdocuments')
        docs_column_names = [col['name'] for col in docs_columns]
        assert 'updated_at' in docs_column_names
        assert 'version' in docs_column_names
        assert 'tenant_id' in docs_column_names
        
        # Check analysischunks table
        chunks_columns = inspector.get_columns('analysischunks')
        chunks_column_names = [col['name'] for col in chunks_columns]
        assert 'updated_at' in chunks_column_names
        assert 'created_at' in chunks_column_names
        assert 'version' in chunks_column_names
        assert 'tenant_id' in chunks_column_names
    
    def test_triggers_exist(self, db_engine):
        """Test that update triggers exist"""
        with db_engine.connect() as conn:
            # Check that triggers exist
            result = conn.execute(text("""
                SELECT trigger_name, event_object_table 
                FROM information_schema.triggers 
                WHERE trigger_name LIKE 'update_%_updated_at'
                ORDER BY event_object_table
            """))
            
            triggers = result.fetchall()
            trigger_tables = [row[1] for row in triggers]
            
            # Should have triggers for all tables with updated_at
            assert 'chats' in trigger_tables
            assert 'chatmessages' in trigger_tables
            assert 'analysisdocuments' in trigger_tables
            assert 'analysischunks' in trigger_tables
    
    def test_unique_constraints_exist(self, db_engine):
        """Test that unique constraints exist"""
        from sqlalchemy import inspect
        
        inspector = inspect(db_engine)
        
        # Check chats unique constraints
        chats_indexes = inspector.get_indexes('chats')
        index_names = [idx['name'] for idx in chats_indexes]
        assert 'uq_chats_tenant_owner_name' in index_names
        
        # Check analysischunks unique constraints
        chunks_indexes = inspector.get_indexes('analysischunks')
        chunk_index_names = [idx['name'] for idx in chunks_indexes]
        assert 'uq_analysischunks_tenant_document_idx' in chunk_index_names
        
        # Check analysisdocuments unique constraints (partial index)
        with db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'analysisdocuments' 
                AND indexname = 'uq_analysisdocuments_tenant_url'
            """))
            assert result.fetchone() is not None
