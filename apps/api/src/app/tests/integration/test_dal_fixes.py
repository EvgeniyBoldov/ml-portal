"""
Integration tests for DAL fixes and production-grade features
"""
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.repositories.base_enhanced import (
    TenantScopedRepository, NotFoundError, DuplicateError, 
    ConcurrencyError, ForeignKeyViolationError
)
from app.repositories.chats_repo import ChatsRepository, ChatMessagesRepository
from app.repositories.idempotency_repo import IdempotencyRepository
from app.core.uow import UnitOfWork, TransactionManager
from app.models.chat import Chats, ChatMessages


class TestTenantIsolation:
    """Test tenant isolation in repositories"""
    
    def test_chats_repository_tenant_isolation(self, db_session: Session):
        """Test that chats are isolated by tenant"""
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create chats in different tenants
        chat1 = chats_repo.create_chat(tenant1, user_id, "Chat 1")
        chat2 = chats_repo.create_chat(tenant2, user_id, "Chat 1")  # Same name, different tenant
        
        # Both should exist
        assert chat1.id is not None
        assert chat2.id is not None
        assert chat1.name == chat2.name
        assert chat1.tenant_id != chat2.tenant_id
        
        # Query by tenant should return only tenant's chats
        tenant1_chats, _ = chats_repo.get_user_chats(tenant1, user_id)
        tenant2_chats, _ = chats_repo.get_user_chats(tenant2, user_id)
        
        assert len(tenant1_chats) == 1
        assert len(tenant2_chats) == 1
        assert tenant1_chats[0].id == chat1.id
        assert tenant2_chats[0].id == chat2.id
    
    def test_chat_messages_repository_tenant_isolation(self, db_session: Session):
        """Test that chat messages are isolated by tenant"""
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        messages_repo = ChatMessagesRepository(db_session)
        
        # Create chats in different tenants
        chat1 = chats_repo.create_chat(tenant1, user_id, "Chat 1")
        chat2 = chats_repo.create_chat(tenant2, user_id, "Chat 2")
        
        # Create messages for each chat
        msg1 = messages_repo.create_message(
            tenant1, chat1.id, "user", {"text": "Hello from tenant 1"}
        )
        msg2 = messages_repo.create_message(
            tenant2, chat2.id, "user", {"text": "Hello from tenant 2"}
        )
        
        # Messages should be isolated by tenant
        tenant1_messages, _ = messages_repo.get_chat_messages(tenant1, chat1.id)
        tenant2_messages, _ = messages_repo.get_chat_messages(tenant2, chat2.id)
        
        assert len(tenant1_messages) == 1
        assert len(tenant2_messages) == 1
        assert tenant1_messages[0].content["text"] == "Hello from tenant 1"
        assert tenant2_messages[0].content["text"] == "Hello from tenant 2"


class TestOptimisticLocking:
    """Test optimistic locking with version field"""
    
    def test_chat_update_with_optimistic_locking(self, db_session: Session):
        """Test optimistic locking on chat updates"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create chat
        chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
        original_version = chat.version
        
        # Update with correct version
        updated_chat = chats_repo.update_chat_name(
            tenant_id, chat.id, "Updated Chat", original_version
        )
        
        assert updated_chat is not None
        assert updated_chat.name == "Updated Chat"
        assert updated_chat.version == original_version + 1
        
        # Try to update with old version - should fail
        with pytest.raises(ConcurrencyError):
            chats_repo.update_chat_name(
                tenant_id, chat.id, "Another Update", original_version
            )
    
    def test_concurrent_updates_detection(self, db_session: Session):
        """Test detection of concurrent updates"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create chat
        chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
        
        # Simulate concurrent update by manually incrementing version
        chat.version += 1
        db_session.flush()
        
        # Try to update with old version
        with pytest.raises(ConcurrencyError):
            chats_repo.update_chat_name(
                tenant_id, chat.id, "Concurrent Update", chat.version - 1
            )


class TestCursorPagination:
    """Test cursor-based pagination"""
    
    def test_chats_cursor_pagination(self, db_session: Session):
        """Test cursor-based pagination for chats"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create multiple chats
        chats = []
        for i in range(5):
            chat = chats_repo.create_chat(tenant_id, user_id, f"Chat {i}")
            chats.append(chat)
        
        # Test pagination
        page1_chats, next_cursor = chats_repo.get_user_chats(tenant_id, user_id, limit=2)
        assert len(page1_chats) == 2
        assert next_cursor is not None
        
        # Get next page
        page2_chats, next_cursor2 = chats_repo.get_user_chats(
            tenant_id, user_id, limit=2, cursor=next_cursor
        )
        assert len(page2_chats) == 2
        assert next_cursor2 is not None
        
        # Get final page
        page3_chats, next_cursor3 = chats_repo.get_user_chats(
            tenant_id, user_id, limit=2, cursor=next_cursor2
        )
        assert len(page3_chats) == 1
        assert next_cursor3 is None
        
        # Verify no duplicates
        all_chat_ids = [c.id for c in page1_chats + page2_chats + page3_chats]
        assert len(set(all_chat_ids)) == len(all_chat_ids)
    
    def test_cursor_stability(self, db_session: Session):
        """Test cursor stability when new records are added"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create initial chats
        chat1 = chats_repo.create_chat(tenant_id, user_id, "Chat 1")
        chat2 = chats_repo.create_chat(tenant_id, user_id, "Chat 2")
        
        # Get first page
        page1_chats, next_cursor = chats_repo.get_user_chats(tenant_id, user_id, limit=1)
        assert len(page1_chats) == 1
        assert page1_chats[0].id == chat2.id  # Most recent first
        
        # Add new chat
        chat3 = chats_repo.create_chat(tenant_id, user_id, "Chat 3")
        
        # Get next page with same cursor - should not include new chat
        page2_chats, _ = chats_repo.get_user_chats(tenant_id, user_id, limit=1, cursor=next_cursor)
        assert len(page2_chats) == 1
        assert page2_chats[0].id == chat1.id  # Should get the older chat


class TestBulkOperations:
    """Test bulk operations"""
    
    def test_bulk_create_messages(self, db_session: Session):
        """Test bulk creation of messages"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        messages_repo = ChatMessagesRepository(db_session)
        
        # Create chat
        chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
        
        # Prepare bulk messages data
        messages_data = []
        for i in range(5):
            messages_data.append({
                'chat_id': chat.id,
                'role': 'user',
                'content': {'text': f'Message {i}'},
                'meta': {'index': i}
            })
        
        # Bulk create messages
        messages = messages_repo.bulk_create_messages(tenant_id, messages_data)
        
        assert len(messages) == 5
        for i, message in enumerate(messages):
            assert message.content['text'] == f'Message {i}'
            assert message.meta['index'] == i


class TestErrorMapping:
    """Test error mapping from database to domain errors"""
    
    def test_duplicate_error_mapping(self, db_session: Session):
        """Test mapping of duplicate errors"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create chat with specific name
        chat = chats_repo.create_chat(tenant_id, user_id, "Unique Chat")
        
        # Try to create another chat with same name for same user
        with pytest.raises(DuplicateError):
            chats_repo.create_chat(tenant_id, user_id, "Unique Chat")
    
    def test_not_found_error_mapping(self, db_session: Session):
        """Test mapping of not found errors"""
        tenant_id = uuid.uuid4()
        non_existent_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Try to update non-existent chat
        with pytest.raises(NotFoundError):
            chats_repo.update_chat_name(tenant_id, non_existent_id, "New Name", 1)


class TestTransactionManagement:
    """Test transaction management with Unit of Work"""
    
    def test_unit_of_work_success(self, db_session: Session):
        """Test successful transaction with Unit of Work"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        uow = UnitOfWork(db_session)
        
        with uow:
            chats_repo = uow.get_repository(ChatsRepository)
            messages_repo = uow.get_repository(ChatMessagesRepository)
            
            # Create chat
            chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
            
            # Create message
            message = messages_repo.create_message(
                tenant_id, chat.id, "user", {"text": "Hello"}
            )
            
            # Update chat
            chats_repo.update_last_message_at(tenant_id, chat.id, message.created_at)
        
        # Verify everything was committed
        assert chat.id is not None
        assert message.id is not None
        
        # Verify chat was updated
        updated_chat = chats_repo.get_by_id(tenant_id, chat.id)
        assert updated_chat.last_message_at == message.created_at
    
    def test_unit_of_work_rollback(self, db_session: Session):
        """Test rollback on error with Unit of Work"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        uow = UnitOfWork(db_session)
        
        try:
            with uow:
                chats_repo = uow.get_repository(ChatsRepository)
                
                # Create chat
                chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
                
                # Force an error
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # Verify chat was not committed
        chats_repo = ChatsRepository(db_session)
        retrieved_chat = chats_repo.get_by_id(tenant_id, chat.id)
        assert retrieved_chat is None


class TestIdempotencyRepository:
    """Test idempotency repository"""
    
    def test_idempotency_key_storage_and_retrieval(self, db_session: Session):
        """Test storing and retrieving idempotency keys"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        idempotency_repo = IdempotencyRepository(db_session)
        
        # Store response
        key = "test-key-123"
        method = "POST"
        path = "/api/v1/chats"
        body = {"name": "Test Chat"}
        
        stored_key = idempotency_repo.store_response(
            tenant_id, user_id, key, method, path, body,
            response_status=200,
            response_body={"chat_id": "123"},
            ttl_minutes=15
        )
        
        assert stored_key.key == key
        assert stored_key.response_status == 200
        
        # Retrieve response
        retrieved_key = idempotency_repo.get_response(
            tenant_id, user_id, key, method, path, body
        )
        
        assert retrieved_key is not None
        assert retrieved_key.response_status == 200
        assert retrieved_key.response_body["chat_id"] == "123"
    
    def test_idempotency_key_expiry(self, db_session: Session):
        """Test idempotency key expiry"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        idempotency_repo = IdempotencyRepository(db_session)
        
        # Store response with very short TTL
        key = "test-key-expiry"
        method = "POST"
        path = "/api/v1/chats"
        body = {"name": "Test Chat"}
        
        idempotency_repo.store_response(
            tenant_id, user_id, key, method, path, body,
            response_status=200,
            ttl_minutes=0  # Expired immediately
        )
        
        # Try to retrieve - should return None due to expiry
        retrieved_key = idempotency_repo.get_response(
            tenant_id, user_id, key, method, path, body
        )
        
        assert retrieved_key is None


class TestRepositoryFilters:
    """Test advanced filtering capabilities"""
    
    def test_complex_filters(self, db_session: Session):
        """Test complex filtering with operators"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create chats with different creation times
        now = datetime.now(timezone.utc)
        chat1 = chats_repo.create_chat(tenant_id, user_id, "Chat 1")
        chat2 = chats_repo.create_chat(tenant_id, user_id, "Chat 2")
        
        # Test date range filter
        filters = {
            'created_at': {
                'gte': now.replace(hour=0, minute=0, second=0, microsecond=0)
            }
        }
        
        chats, _ = chats_repo.list(tenant_id, filters=filters)
        assert len(chats) >= 2
        
        # Test multiple filters
        filters = {
            'owner_id': user_id,
            'name': {'like': 'Chat%'}
        }
        
        chats, _ = chats_repo.list(tenant_id, filters=filters)
        assert len(chats) == 2
        assert all(chat.name.startswith('Chat') for chat in chats)
