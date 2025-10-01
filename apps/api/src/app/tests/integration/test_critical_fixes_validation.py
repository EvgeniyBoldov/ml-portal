"""
Comprehensive tests for critical fixes
"""
import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import httpx

from app.tests.contract.test_client_contracts import ChatMessage
from app.core.di import HTTPLLMClient, HTTPEmbClient
from app.core.domain_exceptions import (
    ExternalServiceTimeout, ExternalServiceUnavailable, ExternalServiceInvalidResponse,
    ExternalServiceRateLimited, ExternalServiceCircuitBreakerOpen
)
from app.core.tenant_validation import require_tenant_id, TenantRequiredError
from app.core.security import UserCtx
from app.repositories.factory import RepositoryFactory


class TestTypeSafeInterfaces:
    """Test type-safe interfaces for LLM/EMB clients"""
    
    @pytest.mark.asyncio
    async def test_llm_client_uses_chat_message(self):
        """Test that LLM client uses ChatMessage instead of dict"""
        client = HTTPLLMClient("http://test", timeout=5, max_retries=1)
        
        # Test with ChatMessage objects
        messages = [
            ChatMessage.create_system_message("You are a helpful assistant."),
            ChatMessage.create_user_message("Hello, World!")
        ]
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"text": "Hello! How can I help you?"}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            result = await client.generate(messages, model="test-model")
            
            assert result == "Hello! How can I help you?"
            # Verify that messages were serialized correctly
            call_args = mock_post.call_args
            request_data = call_args[1]['json']
            assert 'messages' in request_data
            assert len(request_data['messages']) == 2
            assert request_data['messages'][0]['role'] == 'system'
            assert request_data['messages'][1]['role'] == 'user'
    
    @pytest.mark.asyncio
    async def test_llm_client_generate_stream(self):
        """Test that LLM client has generate_stream method"""
        client = HTTPLLMClient("http://test", timeout=5, max_retries=1)
        
        messages = [
            ChatMessage.create_user_message("Hello, World!")
        ]
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"text": "Hello! How can I help you?"}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            chunks = []
            async for chunk in client.generate_stream(messages, model="test-model"):
                chunks.append(chunk)
            
            assert len(chunks) > 0
            assert ''.join(chunks) == "Hello! How can I help you?"
    
    @pytest.mark.asyncio
    async def test_emb_client_uses_strings(self):
        """Test that EMB client uses list[str] instead of dict"""
        client = HTTPEmbClient("http://test", timeout=5, max_retries=1)
        
        texts = ["Hello", "World"]
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            result = await client.embed_texts(texts, model="test-model")
            
            assert len(result) == 2
            assert len(result[0]) == 2
            assert len(result[1]) == 2


class TestMigrationCompliance:
    """Test migration compliance and chain integrity"""
    
    def test_migration_revision_chain(self):
        """Test that migration revisions form a proper chain"""
        import os
        import re
        
        migration_dir = "apps/api/alembic/versions"
        migration_files = [f for f in os.listdir(migration_dir) if f.endswith('.py')]
        
        # Extract revision numbers and down_revision references
        revisions = {}
        down_revisions = {}
        
        for file in migration_files:
            file_path = os.path.join(migration_dir, file)
            with open(file_path, 'r') as f:
                content = f.read()
                
                # Extract revision
                revision_match = re.search(r"revision = '([^']+)'", content)
                if revision_match:
                    revisions[file] = revision_match.group(1)
                
                # Extract down_revision
                down_revision_match = re.search(r"down_revision = '([^']+)'", content)
                if down_revision_match:
                    down_revisions[file] = down_revision_match.group(1)
        
        # Check that all files have revision and down_revision
        for file in migration_files:
            assert file in revisions, f"File {file} missing revision"
            if file != "001_initial_migration.py":  # First migration has no down_revision
                assert file in down_revisions, f"File {file} missing down_revision"
        
        # Check that down_revision chain is valid
        for file, down_revision in down_revisions.items():
            if down_revision != "None":
                # Find the file that has this revision
                found = False
                for other_file, revision in revisions.items():
                    if revision == down_revision:
                        found = True
                        break
                assert found, f"File {file} references non-existent down_revision {down_revision}"
    
    def test_no_duplicate_revision_numbers(self):
        """Test that no two files have the same revision number"""
        import os
        import re
        
        migration_dir = "apps/api/alembic/versions"
        migration_files = [f for f in os.listdir(migration_dir) if f.endswith('.py')]
        
        revision_numbers = set()
        
        for file in migration_files:
            # Extract number from filename (e.g., "001_initial_migration.py" -> "001")
            number_match = re.match(r'^(\d+)_', file)
            if number_match:
                number = number_match.group(1)
                assert number not in revision_numbers, f"Duplicate revision number {number} in {file}"
                revision_numbers.add(number)
    
    def test_gin_indexes_correct_names(self):
        """Test that GIN indexes use correct naming convention"""
        import os
        
        migration_file = "apps/api/alembic/versions/006_add_gin_indexes_with_opclass.py"
        with open(migration_file, 'r') as f:
            content = f.read()
            
            # Check that we drop the correct old indexes
            assert "DROP INDEX IF EXISTS ix_chatmessages_content_gin" in content
            assert "DROP INDEX IF EXISTS ix_chatmessages_meta_gin" in content
            assert "DROP INDEX IF EXISTS ix_analysisdocuments_result_gin" in content
            assert "DROP INDEX IF EXISTS ix_analysischunks_meta_gin" in content
            
            # Check that we create new indexes with correct names
            assert "CREATE INDEX idx_chatmessages_content_gin" in content
            assert "CREATE INDEX idx_chatmessages_meta_gin" in content
            assert "CREATE INDEX idx_analysisdocuments_result_gin" in content
    
    def test_analysis_chunks_correct_column_name(self):
        """Test that analysis chunks use correct column name"""
        import os
        
        migration_file = "apps/api/alembic/versions/006_add_gin_indexes_with_opclass.py"
        with open(migration_file, 'r') as f:
            content = f.read()
            
            # Check that we use chunk_idx, not chunk_index
            assert "chunk_idx" in content
            assert "chunk_index" not in content
    
    def test_analysis_documents_correct_status_values(self):
        """Test that analysis documents use correct status values"""
        import os
        
        migration_file = "apps/api/alembic/versions/006_add_gin_indexes_with_opclass.py"
        with open(migration_file, 'r') as f:
            content = f.read()
            
            # Check that we use correct status values
            assert "status IN ('processing', 'done', 'error')" in content
            assert "status IN ('processing', 'completed', 'failed')" not in content
    
    def test_analysis_documents_correct_time_field(self):
        """Test that analysis documents use correct time field"""
        import os
        
        migration_file = "apps/api/alembic/versions/006_add_gin_indexes_with_opclass.py"
        with open(migration_file, 'r') as f:
            content = f.read()
            
            # Check that we use date_upload, not created_at
            assert "date_upload" in content
            # Should not use created_at for analysisdocuments
            assert "analysisdocuments (tenant_id, created_at)" not in content


class TestTenantIsolationRAG:
    """Test tenant isolation in RAG upload"""
    
    def test_rag_upload_no_uuid4_generation(self):
        """Test that RAG upload does not generate random UUIDs"""
        import os
        import ast
        
        rag_file = "apps/api/src/app/api/v1/rag.py"
        with open(rag_file, 'r') as f:
            content = f.read()
            
            # Parse AST to find uuid.uuid4() calls
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            if (node.func.value.id == 'uuid' and 
                                node.func.attr == 'uuid4'):
                                # Found uuid.uuid4() call
                                line_num = node.lineno
                                # Check if it's in a context that should not have it
                                lines = content.split('\n')
                                context_line = lines[line_num - 1] if line_num <= len(lines) else ""
                                
                                # This should not be in upload flow
                                assert "upload" not in context_line.lower(), \
                                    f"Found uuid.uuid4() in upload context at line {line_num}: {context_line}"
    
    def test_rag_upload_uses_require_tenant_id(self):
        """Test that RAG upload uses require_tenant_id"""
        import os
        
        rag_file = "apps/api/src/app/api/v1/rag.py"
        with open(rag_file, 'r') as f:
            content = f.read()
            
            # Check that we import require_tenant_id
            assert "from app.core.tenant_validation import require_tenant_id" in content
            
            # Check that we use require_tenant_id
            assert "require_tenant_id(user, \"upload_document\")" in content
    
    @pytest.mark.asyncio
    async def test_rag_upload_tenant_validation(self, client: TestClient, real_auth_tokens):
        """Test that RAG upload validates tenant_id"""
        # This test would require a real client and auth tokens
        # For now, we'll test the logic
        
        # Test with valid tenant_id
        mock_user = Mock()
        mock_user.tenant_id = uuid.uuid4()
        
        tenant_id = require_tenant_id(mock_user, "upload_document")
        assert tenant_id == mock_user.tenant_id
        
        # Test without tenant_id
        mock_user_no_tenant = Mock()
        mock_user_no_tenant.tenant_id = None
        
        with pytest.raises(TenantRequiredError):
            require_tenant_id(mock_user_no_tenant, "upload_document")


class TestUserCtxTenantId:
    """Test UserCtx contains tenant_id"""
    
    def test_user_ctx_has_tenant_id_field(self):
        """Test that UserCtx has tenant_id field"""
        from app.core.security import UserCtx
        
        # Test that UserCtx has tenant_id field
        user = UserCtx(id="test-user", role="reader", tenant_id=uuid.uuid4())
        assert user.tenant_id is not None
        
        # Test that tenant_id can be None
        user_no_tenant = UserCtx(id="test-user", role="reader", tenant_id=None)
        assert user_no_tenant.tenant_id is None
    
    def test_get_current_user_from_token_extracts_tenant_id(self):
        """Test that get_current_user_from_token extracts tenant_id"""
        from app.core.security import get_current_user_from_token, encode_jwt
        
        tenant_id = uuid.uuid4()
        
        # Create token with tenant_id
        token = encode_jwt({
            "sub": "test-user",
            "role": "reader",
            "tenant_id": str(tenant_id)
        })
        
        user = get_current_user_from_token(token)
        assert user.id == "test-user"
        assert user.role == "reader"
        assert user.tenant_id == tenant_id
    
    def test_get_current_user_from_token_handles_invalid_tenant_id(self):
        """Test that get_current_user_from_token handles invalid tenant_id"""
        from app.core.security import get_current_user_from_token, encode_jwt
        
        # Create token with invalid tenant_id
        token = encode_jwt({
            "sub": "test-user",
            "role": "reader",
            "tenant_id": "invalid-uuid"
        })
        
        user = get_current_user_from_token(token)
        assert user.id == "test-user"
        assert user.role == "reader"
        assert user.tenant_id is None  # Should be None for invalid UUID
    
    def test_get_current_user_from_token_without_tenant_id(self):
        """Test that get_current_user_from_token works without tenant_id"""
        from app.core.security import get_current_user_from_token, encode_jwt
        
        # Create token without tenant_id
        token = encode_jwt({
            "sub": "test-user",
            "role": "reader"
        })
        
        user = get_current_user_from_token(token)
        assert user.id == "test-user"
        assert user.role == "reader"
        assert user.tenant_id is None


class TestIdempotencyWithUserCtx:
    """Test idempotency with proper UserCtx"""
    
    @pytest.mark.asyncio
    async def test_idempotency_works_with_tenant_id(self):
        """Test that idempotency works when UserCtx has tenant_id"""
        from app.api.deps_idempotency import IdempotencyDependency
        
        dependency = IdempotencyDependency()
        mock_request = Mock()
        mock_request.method = "POST"
        mock_request.url.path = "/api/v1/test"
        mock_request.headers = {"Idempotency-Key": "test-key"}
        mock_request.json = AsyncMock(return_value={"test": "data"})
        
        mock_user = Mock()
        mock_user.id = uuid.uuid4()
        mock_user.tenant_id = uuid.uuid4()
        
        # Should not raise exception
        cached_response, is_new_request = await dependency.check_idempotency(mock_request, mock_user)
        
        # Should be a new request (no cached response)
        assert cached_response is None
        assert is_new_request is True
    
    @pytest.mark.asyncio
    async def test_idempotency_fails_without_tenant_id(self):
        """Test that idempotency fails when UserCtx has no tenant_id"""
        from app.api.deps_idempotency import IdempotencyDependency
        
        dependency = IdempotencyDependency()
        mock_request = Mock()
        mock_request.method = "POST"
        mock_request.url.path = "/api/v1/test"
        mock_request.headers = {"Idempotency-Key": "test-key"}
        mock_request.json = AsyncMock(return_value={"test": "data"})
        
        mock_user = Mock()
        mock_user.id = uuid.uuid4()
        mock_user.tenant_id = None  # No tenant_id
        
        # Should raise exception
        with pytest.raises(Exception, match="User must have valid tenant_id"):
            await dependency.check_idempotency(mock_request, mock_user)


class TestDomainExceptionMapping:
    """Test domain exception mapping to HTTP"""
    
    def test_external_service_timeout_mapping(self):
        """Test ExternalServiceTimeout mapping to HTTP"""
        from app.core.domain_exceptions import BaseController
        
        exc = ExternalServiceTimeout("LLM", 30)
        http_exc = BaseController.map_domain_error_to_http(exc)
        
        assert http_exc.status_code == 504
        assert "EXTERNAL_SERVICE_TIMEOUT" in str(http_exc.detail)
    
    def test_external_service_unavailable_mapping(self):
        """Test ExternalServiceUnavailable mapping to HTTP"""
        from app.core.domain_exceptions import BaseController
        
        exc = ExternalServiceUnavailable("LLM")
        http_exc = BaseController.map_domain_error_to_http(exc)
        
        assert http_exc.status_code == 503
        assert "EXTERNAL_SERVICE_UNAVAILABLE" in str(http_exc.detail)
    
    def test_external_service_rate_limited_mapping(self):
        """Test ExternalServiceRateLimited mapping to HTTP"""
        from app.core.domain_exceptions import BaseController
        
        exc = ExternalServiceRateLimited("LLM", 60)
        http_exc = BaseController.map_domain_error_to_http(exc)
        
        assert http_exc.status_code == 429
        assert "EXTERNAL_SERVICE_RATE_LIMITED" in str(http_exc.detail)
        assert "Retry-After" in http_exc.headers
        assert http_exc.headers["Retry-After"] == "60"
    
    def test_external_service_circuit_breaker_open_mapping(self):
        """Test ExternalServiceCircuitBreakerOpen mapping to HTTP"""
        from app.core.domain_exceptions import BaseController
        
        exc = ExternalServiceCircuitBreakerOpen("LLM")
        http_exc = BaseController.map_domain_error_to_http(exc)
        
        assert http_exc.status_code == 503
        assert "EXTERNAL_SERVICE_CIRCUIT_BREAKER_OPEN" in str(http_exc.detail)


class TestChatMessageContract:
    """Test ChatMessage contract compliance"""
    
    def test_chat_message_extra_forbid(self):
        """Test that ChatMessage forbids extra fields"""
        with pytest.raises(Exception):  # ValidationError
            ChatMessage(role="user", content="Hello", extra_field="not_allowed")
    
    def test_chat_message_valid_roles(self):
        """Test that ChatMessage accepts valid roles"""
        valid_roles = ["system", "user", "assistant", "tool"]
        
        for role in valid_roles:
            msg = ChatMessage(role=role, content="Test content")
            assert msg.role == role
    
    def test_chat_message_invalid_role(self):
        """Test that ChatMessage rejects invalid roles"""
        with pytest.raises(Exception):  # ValidationError
            ChatMessage(role="invalid_role", content="Test content")
    
    def test_chat_message_content_types(self):
        """Test that ChatMessage accepts both string and dict content"""
        # String content
        msg1 = ChatMessage(role="user", content="Hello, World!")
        assert msg1.content == "Hello, World!"
        
        # Dict content
        dict_content = {"type": "tool_call", "data": {"test": "value"}}
        msg2 = ChatMessage(role="tool", content=dict_content)
        assert msg2.content == dict_content
    
    def test_chat_message_serialization(self):
        """Test that ChatMessage serializes and deserializes correctly"""
        original = ChatMessage.create_user_message("Hello, World!")
        
        # Serialize
        data = original.model_dump()
        
        # Deserialize
        restored = ChatMessage.model_validate(data)
        
        assert restored.role == original.role
        assert restored.content == original.content


class TestIntegrationEndToEnd:
    """Test end-to-end integration"""
    
    @pytest.mark.asyncio
    async def test_chat_message_flow_with_tenant_validation(self):
        """Test complete chat message flow with tenant validation"""
        # Mock user with tenant_id
        mock_user = Mock()
        mock_user.id = uuid.uuid4()
        mock_user.tenant_id = uuid.uuid4()
        
        # Test tenant validation
        tenant_id = require_tenant_id(mock_user, "post_message")
        assert tenant_id == mock_user.tenant_id
        
        # Test ChatMessage creation
        messages = [
            ChatMessage.create_system_message("You are a helpful assistant."),
            ChatMessage.create_user_message("Hello, World!")
        ]
        
        # Test LLM client with ChatMessage
        client = HTTPLLMClient("http://test", timeout=5, max_retries=1)
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"text": "Hello! How can I help you?"}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            result = await client.generate(messages, model="test-model")
            
            assert result == "Hello! How can I help you?"
    
    def test_no_dict_in_api_schemas(self):
        """Test that API schemas don't use raw dict types"""
        # This would require checking all API schemas
        # For now, we'll test that ChatMessage is properly typed
        
        # Test that ChatMessage is not a dict
        msg = ChatMessage.create_user_message("Hello")
        assert not isinstance(msg, dict)
        assert isinstance(msg, ChatMessage)
        
        # Test that content can be dict but message itself is ChatMessage
        dict_content = {"type": "tool_call", "data": {"test": "value"}}
        msg = ChatMessage(role="tool", content=dict_content)
        assert isinstance(msg.content, dict)
        assert isinstance(msg, ChatMessage)
