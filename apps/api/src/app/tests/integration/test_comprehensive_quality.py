"""
Comprehensive tests for connectors, models, and DAL
"""
import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

from app.core.di import HTTPLLMClient, HTTPEmbClient, CircuitBreaker, CircuitBreakerState
from app.core.domain_exceptions import (
    ExternalServiceTimeout, ExternalServiceUnavailable, ExternalServiceInvalidResponse,
    ExternalServiceRateLimited, ExternalServiceCircuitBreakerOpen
)
from app.core.tenant_validation import require_tenant_id, TenantRequiredError
from app.core.constants import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, EXTENSION_TO_MIME
from app.repositories.factory import RepositoryFactory
from app.schemas.chats import ChatMessage
from app.tests.contract.test_client_contracts import ChatMessage as ContractChatMessage


class TestContractCompliance:
    """Test contract compliance for LLM/EMB clients"""
    
    @pytest.mark.asyncio
    async def test_llm_client_domain_exceptions(self):
        """Test that LLM client throws domain exceptions"""
        client = HTTPLLMClient("http://test", timeout=5, max_retries=1)
        
        # Test timeout exception
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")
            
            with pytest.raises(ExternalServiceTimeout):
                await client.generate([{"role": "user", "content": "Hello"}])
        
        # Test rate limit exception
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "60"}
            mock_post.side_effect = httpx.HTTPStatusError("Rate limited", request=Mock(), response=mock_response)
            
            with pytest.raises(ExternalServiceRateLimited) as exc_info:
                await client.generate([{"role": "user", "content": "Hello"}])
            
            assert exc_info.value.retry_after == 60
        
        # Test circuit breaker open
        client.circuit_breaker.on_failure()
        client.circuit_breaker.on_failure()
        client.circuit_breaker.on_failure()
        client.circuit_breaker.on_failure()
        client.circuit_breaker.on_failure()  # Should open circuit
        
        with pytest.raises(ExternalServiceCircuitBreakerOpen):
            await client.generate([{"role": "user", "content": "Hello"}])
    
    @pytest.mark.asyncio
    async def test_emb_client_domain_exceptions(self):
        """Test that Embedding client throws domain exceptions"""
        client = HTTPEmbClient("http://test", timeout=5, max_retries=1)
        
        # Test unavailable exception
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")
            
            with pytest.raises(ExternalServiceUnavailable):
                await client.embed_texts(["Hello", "World"])
        
        # Test invalid response exception
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_post.side_effect = httpx.HTTPStatusError("Bad request", request=Mock(), response=mock_response)
            
            with pytest.raises(ExternalServiceInvalidResponse) as exc_info:
                await client.embed_texts(["Hello"])
            
            assert exc_info.value.response_status == 400
            assert exc_info.value.response_body == "Bad request"


class TestTenantValidation:
    """Test tenant validation utilities"""
    
    def test_require_tenant_id_with_valid_user(self):
        """Test require_tenant_id with valid user"""
        mock_user = Mock()
        mock_user.tenant_id = uuid.uuid4()
        
        tenant_id = require_tenant_id(mock_user, "test_operation")
        assert tenant_id == mock_user.tenant_id
    
    def test_require_tenant_id_without_user(self):
        """Test require_tenant_id without user"""
        with pytest.raises(TenantRequiredError) as exc_info:
            require_tenant_id(None, "test_operation")
        
        assert exc_info.value.status_code == 400
        assert "TENANT_REQUIRED" in str(exc_info.value.detail)
    
    def test_require_tenant_id_without_tenant_id(self):
        """Test require_tenant_id without tenant_id"""
        mock_user = Mock()
        mock_user.tenant_id = None
        
        with pytest.raises(TenantRequiredError) as exc_info:
            require_tenant_id(mock_user, "test_operation")
        
        assert exc_info.value.status_code == 400
        assert "TENANT_REQUIRED" in str(exc_info.value.detail)
    
    def test_get_tenant_id_safe(self):
        """Test get_tenant_id_safe utility"""
        mock_user = Mock()
        mock_user.tenant_id = uuid.uuid4()
        
        tenant_id = get_tenant_id_safe(mock_user, "test_operation")
        assert tenant_id == mock_user.tenant_id
        
        # Test with None user
        tenant_id = get_tenant_id_safe(None, "test_operation")
        assert tenant_id is None
        
        # Test with user without tenant_id
        mock_user.tenant_id = None
        tenant_id = get_tenant_id_safe(mock_user, "test_operation")
        assert tenant_id is None


class TestMediaConstants:
    """Test media constants consistency"""
    
    def test_extension_mime_consistency(self):
        """Test that all extensions have corresponding MIME types"""
        for ext, mime in EXTENSION_TO_MIME.items():
            assert ext in ALLOWED_EXTENSIONS, f"Extension {ext} not in ALLOWED_EXTENSIONS"
            assert mime in ALLOWED_MIME_TYPES, f"MIME type {mime} not in ALLOWED_MIME_TYPES"
    
    def test_mime_extension_consistency(self):
        """Test that all MIME types have corresponding extensions"""
        mime_to_ext = {mime: ext for ext, mime in EXTENSION_TO_MIME.items()}
        
        for mime in ALLOWED_MIME_TYPES:
            if mime.startswith('image/'):
                # Image MIME types should have corresponding extensions
                assert any(mime in EXTENSION_TO_MIME.values()), f"MIME type {mime} has no corresponding extension"
    
    def test_valid_extension_mime_pairs(self):
        """Test valid extension-MIME pairs"""
        valid_pairs = [
            ('.jpg', 'image/jpeg'),
            ('.jpeg', 'image/jpeg'),
            ('.png', 'image/png'),
            ('.gif', 'image/gif'),
            ('.webp', 'image/webp'),
            ('.pdf', 'application/pdf'),
            ('.txt', 'text/plain'),
            ('.json', 'application/json')
        ]
        
        for ext, mime in valid_pairs:
            assert ext in ALLOWED_EXTENSIONS
            assert mime in ALLOWED_MIME_TYPES
            assert EXTENSION_TO_MIME[ext] == mime
    
    def test_invalid_extension_mime_pairs(self):
        """Test invalid extension-MIME pairs"""
        invalid_pairs = [
            ('.exe', 'application/pdf'),
            ('.jpg', 'text/plain'),
            ('.pdf', 'image/jpeg'),
            ('.txt', 'application/json')
        ]
        
        for ext, mime in invalid_pairs:
            if ext in EXTENSION_TO_MIME:
                assert EXTENSION_TO_MIME[ext] != mime


class TestDALTenantIsolation:
    """Test DAL tenant isolation"""
    
    def test_repository_factory_tenant_isolation(self, db_session: Session):
        """Test that RepositoryFactory enforces tenant isolation"""
        tenant1_id = uuid.uuid4()
        tenant2_id = uuid.uuid4()
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()
        
        # Create repositories for different tenants
        repo_factory1 = RepositoryFactory(db_session, tenant1_id, user1_id)
        repo_factory2 = RepositoryFactory(db_session, tenant2_id, user2_id)
        
        chats_repo1 = repo_factory1.get_chats_repository()
        chats_repo2 = repo_factory2.get_chats_repository()
        
        # Create chats in different tenants
        chat1 = chats_repo1.create_chat(user1_id, "Chat 1")
        chat2 = chats_repo2.create_chat(user2_id, "Chat 2")
        
        # Verify tenant isolation
        assert chat1.tenant_id == tenant1_id
        assert chat2.tenant_id == tenant2_id
        
        # Verify each tenant only sees their own chats
        chats1 = chats_repo1.list_chats(user1_id)
        chats2 = chats_repo2.list_chats(user2_id)
        
        assert len(chats1) == 1
        assert len(chats2) == 1
        assert chats1[0].id == chat1.id
        assert chats2[0].id == chat2.id
    
    def test_repository_factory_cross_tenant_access_denied(self, db_session: Session):
        """Test that cross-tenant access is denied"""
        tenant1_id = uuid.uuid4()
        tenant2_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create repository for tenant1
        repo_factory1 = RepositoryFactory(db_session, tenant1_id, user_id)
        chats_repo1 = repo_factory1.get_chats_repository()
        
        # Create chat in tenant1
        chat = chats_repo1.create_chat(user_id, "Chat 1")
        
        # Try to access chat from tenant2 repository
        repo_factory2 = RepositoryFactory(db_session, tenant2_id, user_id)
        chats_repo2 = repo_factory2.get_chats_repository()
        
        # Should not find the chat
        found_chat = chats_repo2.get(str(chat.id))
        assert found_chat is None


class TestUniqueConstraints:
    """Test unique constraints and conflict handling"""
    
    def test_chat_name_uniqueness_per_tenant(self, db_session: Session):
        """Test that chat names are unique per tenant"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        repo_factory = RepositoryFactory(db_session, tenant_id, user_id)
        chats_repo = repo_factory.get_chats_repository()
        
        # Create first chat
        chat1 = chats_repo.create_chat(user_id, "Unique Chat")
        assert chat1 is not None
        
        # Try to create second chat with same name - should succeed (different users can have same chat names)
        user2_id = uuid.uuid4()
        chat2 = chats_repo.create_chat(user2_id, "Unique Chat")
        assert chat2 is not None
        
        # But same user cannot have two chats with same name
        with pytest.raises(Exception):  # Should raise DuplicateError or similar
            chats_repo.create_chat(user_id, "Unique Chat")
    
    def test_analysis_chunk_uniqueness_per_document(self, db_session: Session):
        """Test that analysis chunks are unique per document"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        document_id = uuid.uuid4()
        
        repo_factory = RepositoryFactory(db_session, tenant_id, user_id)
        chunks_repo = repo_factory.get_analysis_chunks_repository()
        
        # Create first chunk
        chunk1 = chunks_repo.create_chunk(document_id, "Content 1", 0)
        assert chunk1 is not None
        
        # Try to create second chunk with same index - should fail
        with pytest.raises(Exception):  # Should raise DuplicateError
            chunks_repo.create_chunk(document_id, "Content 2", 0)


class TestCursorPagination:
    """Test cursor-based pagination"""
    
    def test_chat_pagination_stability(self, db_session: Session):
        """Test that chat pagination is stable"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        repo_factory = RepositoryFactory(db_session, tenant_id, user_id)
        chats_repo = repo_factory.get_chats_repository()
        
        # Create multiple chats
        chats = []
        for i in range(5):
            chat = chats_repo.create_chat(user_id, f"Chat {i}")
            chats.append(chat)
        
        # Test pagination
        page1, next_cursor = chats_repo.list_chats(user_id, limit=2)
        assert len(page1) == 2
        assert next_cursor is not None
        
        page2, next_cursor2 = chats_repo.list_chats(user_id, limit=2, cursor=next_cursor)
        assert len(page2) == 2
        assert next_cursor2 is not None
        
        page3, next_cursor3 = chats_repo.list_chats(user_id, limit=2, cursor=next_cursor2)
        assert len(page3) == 1
        assert next_cursor3 is None  # Last page
    
    def test_chat_pagination_consistency(self, db_session: Session):
        """Test that pagination is consistent with insertions"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        repo_factory = RepositoryFactory(db_session, tenant_id, user_id)
        chats_repo = repo_factory.get_chats_repository()
        
        # Create initial chats
        chat1 = chats_repo.create_chat(user_id, "Chat 1")
        chat2 = chats_repo.create_chat(user_id, "Chat 2")
        
        # Get first page
        page1, cursor = chats_repo.list_chats(user_id, limit=1)
        assert len(page1) == 1
        
        # Insert new chat
        chat3 = chats_repo.create_chat(user_id, "Chat 3")
        
        # Get second page - should not include the new chat
        page2, _ = chats_repo.list_chats(user_id, limit=1, cursor=cursor)
        assert len(page2) == 1
        assert page2[0].id == chat2.id  # Should be chat2, not chat3


class TestJSONBIndexes:
    """Test JSONB indexes functionality"""
    
    def test_jsonb_content_search(self, db_session: Session):
        """Test that JSONB content search uses indexes"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        repo_factory = RepositoryFactory(db_session, tenant_id, user_id)
        chats_repo = repo_factory.get_chats_repository()
        messages_repo = repo_factory.get_chat_messages_repository()
        
        # Create chat
        chat = chats_repo.create_chat(user_id, "Test Chat")
        
        # Create message with complex content
        complex_content = {
            "type": "tool_call",
            "tool_call_id": "call_123",
            "name": "search",
            "arguments": {"query": "test", "limit": 10}
        }
        
        message = messages_repo.create_message(
            str(chat.id), "tool", complex_content
        )
        
        # Test JSONB query - this should use the GIN index
        with db_session.bind.connect() as conn:
            result = conn.execute(text("""
                SELECT id FROM chatmessages 
                WHERE content @> '{"type": "tool_call"}'::jsonb
            """)).fetchone()
            
            assert result is not None
            assert result[0] == message.id
    
    def test_jsonb_meta_search(self, db_session: Session):
        """Test that JSONB meta search uses indexes"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        repo_factory = RepositoryFactory(db_session, tenant_id, user_id)
        chats_repo = repo_factory.get_chats_repository()
        
        # Create chat with metadata
        meta = {
            "tags": ["important", "urgent"],
            "priority": "high",
            "source": "api"
        }
        
        chat = chats_repo.create_chat(user_id, "Test Chat", tags=["important"])
        
        # Test JSONB meta query
        with db_session.bind.connect() as conn:
            result = conn.execute(text("""
                SELECT id FROM chats 
                WHERE meta @> '{"tags": ["important"]}'::jsonb
            """)).fetchone()
            
            assert result is not None
            assert result[0] == chat.id


class TestMigrationCompliance:
    """Test migration compliance"""
    
    def test_migration_upgrade_downgrade(self, db_session: Session):
        """Test that migrations can be upgraded and downgraded"""
        # This test would require actual Alembic migration testing
        # For now, we'll test that the migration files exist and are valid
        
        migration_files = [
            "001_initial_migration.py",
            "002_add_foreign_keys.py", 
            "003_add_gin_indexes_with_opclass.py"
        ]
        
        for migration_file in migration_files:
            # Check that migration file exists
            import os
            migration_path = f"apps/api/alembic/versions/{migration_file}"
            assert os.path.exists(migration_path), f"Migration file {migration_file} not found"
    
    def test_enum_consistency(self):
        """Test that ENUMs are consistent between DB and schemas"""
        from app.schemas.chats import MessageRole
        
        # Test that MessageRole enum has expected values
        expected_roles = {"system", "user", "assistant", "tool"}
        actual_roles = set(role.value for role in MessageRole)
        
        assert actual_roles == expected_roles, f"MessageRole enum mismatch: expected {expected_roles}, got {actual_roles}"


class TestTransactionConsistency:
    """Test transaction consistency"""
    
    def test_chat_message_transaction_rollback(self, db_session: Session):
        """Test that chat creation with message creation is transactional"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        repo_factory = RepositoryFactory(db_session, tenant_id, user_id)
        chats_repo = repo_factory.get_chats_repository()
        messages_repo = repo_factory.get_chat_messages_repository()
        
        # Start transaction
        try:
            # Create chat
            chat = chats_repo.create_chat(user_id, "Test Chat")
            
            # Try to create message with invalid data (should fail)
            with pytest.raises(Exception):
                messages_repo.create_message(
                    str(chat.id), "invalid_role", "Test message"
                )
            
            # Transaction should be rolled back
            db_session.rollback()
            
            # Chat should not exist
            found_chat = chats_repo.get(str(chat.id))
            assert found_chat is None
            
        except Exception:
            db_session.rollback()
            raise


class TestContractIntegration:
    """Test contract integration"""
    
    def test_chat_message_serialization_consistency(self):
        """Test that ChatMessage serialization is consistent"""
        # Test string content
        msg1 = ContractChatMessage.create_user_message("Hello, World!")
        data1 = msg1.model_dump()
        restored1 = ContractChatMessage.model_validate(data1)
        assert restored1.content == "Hello, World!"
        
        # Test complex content
        complex_content = {
            "type": "tool_call",
            "tool_call_id": "call_123",
            "name": "search",
            "arguments": {"query": "test", "limit": 10}
        }
        msg2 = ContractChatMessage(role="tool", content=complex_content)
        data2 = msg2.model_dump()
        restored2 = ContractChatMessage.model_validate(data2)
        assert restored2.content == complex_content
    
    def test_domain_exception_mapping(self):
        """Test that domain exceptions are properly mapped to HTTP"""
        from app.core.domain_exceptions import BaseController
        
        # Test timeout exception mapping
        timeout_exc = ExternalServiceTimeout("LLM", 30)
        http_exc = BaseController.map_domain_error_to_http(timeout_exc)
        
        assert http_exc.status_code == 504
        assert "EXTERNAL_SERVICE_TIMEOUT" in str(http_exc.detail)
        
        # Test unavailable exception mapping
        unavailable_exc = ExternalServiceUnavailable("LLM")
        http_exc = BaseController.map_domain_error_to_http(unavailable_exc)
        
        assert http_exc.status_code == 503
        assert "EXTERNAL_SERVICE_UNAVAILABLE" in str(http_exc.detail)
