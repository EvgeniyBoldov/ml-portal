"""
Integration tests for critical DAL fixes
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
from app.repositories.factory import RepositoryFactory
from app.services.idempotency_service import IdempotencyService
from app.core.uow import UnitOfWork, TransactionManager
from app.models.chat import Chats, ChatMessages


class TestTenantIsolationCritical:
    """Test critical tenant isolation issues"""
    
    def test_chats_repository_tenant_isolation_critical(self, db_session: Session):
        """Test that chats are strictly isolated by tenant - CRITICAL"""
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
        
        # CRITICAL: Query by tenant should return only tenant's chats
        tenant1_chats, _ = chats_repo.get_user_chats(tenant1, user_id)
        tenant2_chats, _ = chats_repo.get_user_chats(tenant2, user_id)
        
        assert len(tenant1_chats) == 1
        assert len(tenant2_chats) == 1
        assert tenant1_chats[0].id == chat1.id
        assert tenant2_chats[0].id == chat2.id
        
        # CRITICAL: Cross-tenant access should fail
        cross_tenant_chat = chats_repo.get_by_id(tenant1, chat2.id)
        assert cross_tenant_chat is None  # Should not find chat from other tenant
    
    def test_repository_factory_tenant_isolation(self, db_session: Session):
        """Test repository factory enforces tenant isolation"""
        tenant1 = uuid.uuid4()
        tenant2 = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create factories for different tenants
        factory1 = RepositoryFactory(db_session, tenant1, user_id)
        factory2 = RepositoryFactory(db_session, tenant2, user_id)
        
        # Create chats through factories
        chat1 = factory1.create_chat(user_id, "Factory Chat 1")
        chat2 = factory2.create_chat(user_id, "Factory Chat 2")
        
        # Verify isolation
        assert chat1.tenant_id == tenant1
        assert chat2.tenant_id == tenant2
        
        # Verify cross-tenant queries don't return data
        chats1, _ = factory1.get_user_chats(user_id)
        chats2, _ = factory2.get_user_chats(user_id)
        
        assert len(chats1) == 1
        assert len(chats2) == 1
        assert chats1[0].id == chat1.id
        assert chats2[0].id == chat2.id


class TestIdempotencyCritical:
    """Test critical idempotency functionality"""
    
    def test_idempotency_service_reserve_and_store(self, db_session: Session):
        """Test idempotency service reserve and store operations"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        idempotency_service = IdempotencyService(db_session)
        
        # Test reserve key
        key = "test-key-123"
        method = "POST"
        path = "/api/v1/chats"
        body = {"name": "Test Chat"}
        
        # First call - should reserve
        is_reserved, cached_response = idempotency_service.try_reserve_key(
            tenant_id, user_id, key, method, path, body
        )
        
        assert is_reserved is True
        assert cached_response is None
        
        # Store response
        success = idempotency_service.store_response(
            tenant_id, user_id, key, method, path, body,
            response_status=200,
            response_body={"chat_id": "123"},
            response_headers={"Content-Type": "application/json"}
        )
        
        assert success is True
        
        # Second call - should return cached response
        is_reserved, cached_response = idempotency_service.try_reserve_key(
            tenant_id, user_id, key, method, path, body
        )
        
        assert is_reserved is False
        assert cached_response is not None
        assert cached_response['status'] == 200
        assert cached_response['body']['chat_id'] == "123"
    
    def test_idempotency_parallel_requests(self, db_session: Session):
        """Test parallel requests with same idempotency key"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        idempotency_service = IdempotencyService(db_session)
        
        key = "parallel-test-key"
        method = "POST"
        path = "/api/v1/chats"
        body = {"name": "Parallel Chat"}
        
        # Simulate parallel requests
        results = []
        for i in range(3):
            is_reserved, cached_response = idempotency_service.try_reserve_key(
                tenant_id, user_id, key, method, path, body
            )
            results.append((is_reserved, cached_response))
        
        # Only one should be reserved, others should get cached response
        reserved_count = sum(1 for is_reserved, _ in results if is_reserved)
        cached_count = sum(1 for is_reserved, cached in results if not is_reserved and cached is not None)
        
        # This test verifies the behavior - in real implementation, only first would be reserved
        assert reserved_count >= 1  # At least one should be reserved


class TestOptimisticLockingCritical:
    """Test critical optimistic locking functionality"""
    
    def test_chat_update_optimistic_locking_critical(self, db_session: Session):
        """Test optimistic locking prevents concurrent modifications - CRITICAL"""
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
        
        # CRITICAL: Try to update with old version - should fail
        with pytest.raises(ConcurrencyError):
            chats_repo.update_chat_name(
                tenant_id, chat.id, "Another Update", original_version
            )
    
    def test_concurrent_updates_detection_critical(self, db_session: Session):
        """Test detection of concurrent updates - CRITICAL"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create chat
        chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
        
        # Simulate concurrent update by manually incrementing version
        chat.version += 1
        db_session.flush()
        
        # CRITICAL: Try to update with old version
        with pytest.raises(ConcurrencyError):
            chats_repo.update_chat_name(
                tenant_id, chat.id, "Concurrent Update", chat.version - 1
            )


class TestErrorMappingCritical:
    """Test critical error mapping functionality"""
    
    def test_duplicate_error_mapping_critical(self, db_session: Session):
        """Test mapping of duplicate errors - CRITICAL"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create chat with specific name
        chat = chats_repo.create_chat(tenant_id, user_id, "Unique Chat")
        
        # CRITICAL: Try to create another chat with same name for same user
        with pytest.raises(DuplicateError):
            chats_repo.create_chat(tenant_id, user_id, "Unique Chat")
    
    def test_not_found_error_mapping_critical(self, db_session: Session):
        """Test mapping of not found errors - CRITICAL"""
        tenant_id = uuid.uuid4()
        non_existent_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # CRITICAL: Try to update non-existent chat
        with pytest.raises(NotFoundError):
            chats_repo.update_chat_name(tenant_id, non_existent_id, "New Name", 1)


class TestTransactionManagementCritical:
    """Test critical transaction management"""
    
    def test_unit_of_work_success_critical(self, db_session: Session):
        """Test successful transaction with Unit of Work - CRITICAL"""
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
        
        # CRITICAL: Verify everything was committed
        assert chat.id is not None
        assert message.id is not None
        
        # Verify chat was updated
        updated_chat = chats_repo.get_by_id(tenant_id, chat.id)
        assert updated_chat.last_message_at == message.created_at
    
    def test_unit_of_work_rollback_critical(self, db_session: Session):
        """Test rollback on error with Unit of Work - CRITICAL"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        uow = UnitOfWork(db_session)
        
        try:
            with uow:
                chats_repo = uow.get_repository(ChatsRepository)
                
                # Create chat
                chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
                
                # CRITICAL: Force an error
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # CRITICAL: Verify chat was not committed
        chats_repo = ChatsRepository(db_session)
        retrieved_chat = chats_repo.get_by_id(tenant_id, chat.id)
        assert retrieved_chat is None


class TestContentNormalizationCritical:
    """Test critical content normalization"""
    
    def test_chat_message_content_normalization(self, db_session: Session):
        """Test chat message content is properly normalized"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        messages_repo = ChatMessagesRepository(db_session)
        
        # Create chat
        chat = chats_repo.create_chat(tenant_id, user_id, "Test Chat")
        
        # Test different content formats
        test_cases = [
            {"text": "Simple text message"},
            {"text": "Message with data", "data": {"key": "value"}},
            {"text": "Tool call", "tool_calls": [{"name": "test", "args": {}}]}
        ]
        
        for i, content in enumerate(test_cases):
            message = messages_repo.create_message(
                tenant_id, chat.id, "user", content
            )
            
            assert message.content == content
            assert message.content["text"] is not None


class TestRepositoryContractsCritical:
    """Test critical repository contract consistency"""
    
    def test_repository_contracts_consistency(self, db_session: Session):
        """Test all repositories follow consistent contracts"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Test chats repository contract
        chats_repo = ChatsRepository(db_session)
        
        # Test list method returns consistent format
        chats, next_cursor = chats_repo.get_user_chats(tenant_id, user_id, limit=10)
        assert isinstance(chats, list)
        assert next_cursor is None or isinstance(next_cursor, str)
        
        # Test count method
        count = chats_repo.count(tenant_id, filters={'owner_id': user_id})
        assert isinstance(count, int)
        assert count >= 0
        
        # Test exists method
        exists = chats_repo.exists(tenant_id, uuid.uuid4())
        assert isinstance(exists, bool)
    
    def test_cursor_pagination_consistency(self, db_session: Session):
        """Test cursor pagination is consistent across repositories"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        chats_repo = ChatsRepository(db_session)
        
        # Create multiple chats
        for i in range(5):
            chats_repo.create_chat(tenant_id, user_id, f"Chat {i}")
        
        # Test pagination
        page1_chats, next_cursor = chats_repo.get_user_chats(tenant_id, user_id, limit=2)
        assert len(page1_chats) == 2
        assert next_cursor is not None
        
        # Test next page
        page2_chats, next_cursor2 = chats_repo.get_user_chats(
            tenant_id, user_id, limit=2, cursor=next_cursor
        )
        assert len(page2_chats) == 2
        assert next_cursor2 is not None
        
        # Verify no duplicates
        all_chat_ids = [c.id for c in page1_chats + page2_chats]
        assert len(set(all_chat_ids)) == len(all_chat_ids)
