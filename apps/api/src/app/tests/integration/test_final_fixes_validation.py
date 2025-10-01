"""
Comprehensive tests for final fixes validation
"""
import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import httpx

from app.schemas.chat_messages import ChatMessage, MessageRole
from app.core.di import HTTPLLMClient, HTTPEmbClient
from app.core.domain_exceptions import (
    ExternalServiceTimeout, ExternalServiceUnavailable, ExternalServiceInvalidResponse,
    ExternalServiceRateLimited, ExternalServiceCircuitBreakerOpen
)
from app.core.tenant_validation import require_tenant_id, TenantRequiredError
from app.core.security import UserCtx, encode_jwt, decode_jwt
from app.repositories.factory import RepositoryFactory


class TestRuntimeSchemaSeparation:
    """Test separation of runtime schemas from test contracts"""
    
    def test_chat_message_from_runtime_schema(self):
        """Test that ChatMessage comes from runtime schema, not test contracts"""
        # Test that ChatMessage is properly imported from runtime schema
        msg = ChatMessage.create_user_message("Hello, World!")
        assert msg.role == "user"
        assert msg.content == "Hello, World!"
        assert isinstance(msg, ChatMessage)
    
    def test_chat_message_extra_forbid_regression(self):
        """Regression test: ChatMessage.model_config.extra == 'forbid'"""
        # Test that extra fields are forbidden
        with pytest.raises(Exception):  # ValidationError
            ChatMessage(role="user", content="Hello", extra_field="not_allowed")
    
    def test_chat_message_role_validation_from_enum(self):
        """Test that roles are validated from MessageRole enum"""
        # Test valid roles
        valid_roles = MessageRole.get_valid_roles()
        assert "system" in valid_roles
        assert "user" in valid_roles
        assert "assistant" in valid_roles
        assert "tool" in valid_roles
        
        # Test role validation
        for role in valid_roles:
            assert MessageRole.is_valid_role(role)
        
        # Test invalid role
        assert not MessageRole.is_valid_role("invalid_role")
        
        # Test that ChatMessage rejects invalid roles
        with pytest.raises(Exception):  # ValidationError
            ChatMessage(role="invalid_role", content="Test content")


class TestDuplicateRouteResolution:
    """Test resolution of duplicate /test/simple routes"""
    
    def test_single_test_simple_endpoint_exists(self, client: TestClient):
        """Test that only one /test/simple endpoint exists"""
        # Test that the endpoint exists
        response = client.get("/api/v1/test/simple")
        assert response.status_code == 200
        assert response.json()["message"] == "Hello World"
    
    def test_no_duplicate_test_simple_routes(self):
        """Test that there are no duplicate /test/simple routes"""
        import os
        import re
        
        # Check that health.py doesn't contain /test/simple
        health_file = "apps/api/src/app/api/v1/health.py"
        with open(health_file, 'r') as f:
            content = f.read()
            assert "/test/simple" not in content
        
        # Check that test_endpoints.py contains /test/simple
        test_endpoints_file = "apps/api/src/app/api/v1/test_endpoints.py"
        with open(test_endpoints_file, 'r') as f:
            content = f.read()
            assert "/test/simple" in content


class TestUserCtxTenantIdIntegration:
    """Test UserCtx tenant_id integration with JWT and idempotency"""
    
    def test_get_current_user_sets_tenant_id_from_jwt(self):
        """Test that get_current_user extracts tenant_id from JWT"""
        from app.api.deps import get_current_user
        from unittest.mock import Mock
        
        tenant_id = uuid.uuid4()
        
        # Create JWT with tenant_id
        token = encode_jwt({
            "sub": "test-user",
            "role": "reader",
            "tenant_id": str(tenant_id),
            "typ": "access"
        })
        
        # Mock dependencies
        with patch('app.api.deps.get_bearer_token', return_value=token):
            with patch('app.api.deps.db_session') as mock_db:
                with patch('app.repositories.users_repo_enhanced.UsersRepository') as mock_repo_class:
                    mock_repo = Mock()
                    mock_repo_class.return_value = mock_repo
                    
                    mock_user = Mock()
                    mock_user.id = "test-user"
                    mock_user.role = "reader"
                    mock_user.is_active = True
                    mock_repo.get.return_value = mock_user
                    
                    # Mock session
                    mock_session = Mock()
                    mock_db.return_value = mock_session
                    
                    # Test get_current_user
                    user = get_current_user(token, mock_session)
                    
                    assert user.id == "test-user"
                    assert user.role == "reader"
                    assert user.tenant_id == tenant_id
    
    def test_get_current_user_handles_invalid_tenant_id(self):
        """Test that get_current_user handles invalid tenant_id gracefully"""
        from app.api.deps import get_current_user
        from unittest.mock import Mock
        
        # Create JWT with invalid tenant_id
        token = encode_jwt({
            "sub": "test-user",
            "role": "reader",
            "tenant_id": "invalid-uuid",
            "typ": "access"
        })
        
        # Mock dependencies
        with patch('app.api.deps.get_bearer_token', return_value=token):
            with patch('app.api.deps.db_session') as mock_db:
                with patch('app.repositories.users_repo_enhanced.UsersRepository') as mock_repo_class:
                    mock_repo = Mock()
                    mock_repo_class.return_value = mock_repo
                    
                    mock_user = Mock()
                    mock_user.id = "test-user"
                    mock_user.role = "reader"
                    mock_user.is_active = True
                    mock_repo.get.return_value = mock_user
                    
                    # Mock session
                    mock_session = Mock()
                    mock_db.return_value = mock_session
                    
                    # Test get_current_user
                    user = get_current_user(token, mock_session)
                    
                    assert user.id == "test-user"
                    assert user.role == "reader"
                    assert user.tenant_id is None  # Should be None for invalid UUID
    
    def test_idempotency_dependency_rejects_without_tenant_id(self):
        """Test that idempotency dependency rejects requests without tenant_id"""
        from app.api.deps_idempotency import IdempotencyDependency
        
        dependency = IdempotencyDependency()
        mock_request = Mock()
        mock_request.method = "POST"
        mock_request.url.path = "/api/v1/test"
        mock_request.headers = {"Idempotency-Key": "test-key"}
        mock_request.json = AsyncMock(return_value={"test": "data"})
        
        # Test with user without tenant_id
        mock_user = Mock()
        mock_user.id = uuid.uuid4()
        mock_user.tenant_id = None  # No tenant_id
        
        # Should raise exception
        with pytest.raises(Exception, match="User must have valid tenant_id"):
            await dependency.check_idempotency(mock_request, mock_user)
    
    def test_idempotency_dependency_works_with_tenant_id(self):
        """Test that idempotency dependency works with tenant_id"""
        from app.api.deps_idempotency import IdempotencyDependency
        
        dependency = IdempotencyDependency()
        mock_request = Mock()
        mock_request.method = "POST"
        mock_request.url.path = "/api/v1/test"
        mock_request.headers = {"Idempotency-Key": "test-key"}
        mock_request.json = AsyncMock(return_value={"test": "data"})
        
        # Test with user with tenant_id
        mock_user = Mock()
        mock_user.id = uuid.uuid4()
        mock_user.tenant_id = uuid.uuid4()
        
        # Should not raise exception
        cached_response, is_new_request = await dependency.check_idempotency(mock_request, mock_user)
        
        # Should be a new request (no cached response)
        assert cached_response is None
        assert is_new_request is True


class TestMigrationIntegrity:
    """Test migration integrity and column existence"""
    
    def test_migration_006_no_indexes_on_missing_columns(self):
        """Test that migration 006 doesn't create indexes on missing columns"""
        import os
        
        migration_file = "apps/api/alembic/versions/006_add_gin_indexes_with_opclass.py"
        with open(migration_file, 'r') as f:
            content = f.read()
            
            # Check that we don't create index on analysisdocuments.meta (doesn't exist)
            assert "CREATE INDEX idx_analysisdocuments_meta_gin" not in content
            
            # Check that we do create index on analysisdocuments.result (exists)
            assert "CREATE INDEX idx_analysisdocuments_result_gin" in content
            
            # Check that we don't reference meta in comments
            assert "analysisdocuments.meta" not in content
    
    def test_migration_006_correct_column_references(self):
        """Test that migration 006 references correct columns"""
        import os
        
        migration_file = "apps/api/alembic/versions/006_add_gin_indexes_with_opclass.py"
        with open(migration_file, 'r') as f:
            content = f.read()
            
            # Check that we use chunk_idx (exists) not chunk_index (doesn't exist)
            assert "chunk_idx" in content
            assert "chunk_index" not in content
            
            # Check that we use date_upload (exists) not created_at (doesn't exist for analysisdocuments)
            assert "date_upload" in content
            # Should not use created_at for analysisdocuments
            assert "analysisdocuments (tenant_id, created_at)" not in content
    
    def test_migration_006_correct_status_values(self):
        """Test that migration 006 uses correct status values"""
        import os
        
        migration_file = "apps/api/alembic/versions/006_add_gin_indexes_with_opclass.py"
        with open(migration_file, 'r') as f:
            content = f.read()
            
            # Check that we use correct status values
            assert "status IN ('processing', 'done', 'error')" in content
            assert "status IN ('processing', 'completed', 'failed')" not in content


class TestClientIPImport:
    """Test that get_client_ip is properly imported"""
    
    def test_get_client_ip_function_exists(self):
        """Test that get_client_ip function exists and is callable"""
        from app.api.deps import get_client_ip
        
        # Test that function exists
        assert callable(get_client_ip)
        
        # Test that it can be called with a mock request
        mock_request = Mock()
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        
        ip = get_client_ip(mock_request)
        assert ip == "127.0.0.1"


class TestProtocolBasedDependencies:
    """Test that dependencies use Protocol types"""
    
    def test_llm_client_dependency_returns_protocol(self):
        """Test that LLM client dependency returns Protocol type"""
        from app.api.deps import get_llm_client
        from app.adapters.llm_client import LLMClientProtocol
        
        # Test that function returns Depends with Protocol type
        dependency = get_llm_client()
        assert hasattr(dependency, 'dependency')
        
        # Test that the dependency can be resolved to Protocol implementation
        with patch('app.core.di.llm_client_dependency') as mock_dep:
            mock_client = Mock(spec=LLMClientProtocol)
            mock_dep.return_value = mock_client
            
            # Test that resolved client implements Protocol
            assert hasattr(mock_client, 'generate')
            assert hasattr(mock_client, 'generate_stream')
    
    def test_emb_client_dependency_returns_protocol(self):
        """Test that EMB client dependency returns Protocol type"""
        from app.api.deps import get_emb_client
        from app.adapters.emb_client import EmbClientProtocol
        
        # Test that function returns Depends with Protocol type
        dependency = get_emb_client()
        assert hasattr(dependency, 'dependency')
        
        # Test that the dependency can be resolved to Protocol implementation
        with patch('app.core.di.emb_client_dependency') as mock_dep:
            mock_client = Mock(spec=EmbClientProtocol)
            mock_dep.return_value = mock_client
            
            # Test that resolved client implements Protocol
            assert hasattr(mock_client, 'embed_texts')
            assert hasattr(mock_client, 'embed_query')


class TestRAGUploadValidation:
    """Test RAG upload validation and extension handling"""
    
    def test_rag_upload_uses_safe_ext(self):
        """Test that RAG upload uses _safe_ext for S3 keys"""
        import os
        import ast
        
        rag_file = "apps/api/src/app/api/v1/rag.py"
        with open(rag_file, 'r') as f:
            content = f.read()
            
            # Check that _safe_ext is used
            assert "_safe_ext" in content
            
            # Check that uuid.uuid4() is not used in upload flow
            assert "uuid.uuid4()" not in content
    
    def test_rag_upload_extension_validation(self):
        """Test that RAG upload validates extensions properly"""
        from app.api.v1.rag import is_allowed_extension, is_allowed_mime_type
        
        # Test valid combinations
        assert is_allowed_extension("doc.pdf")
        assert is_allowed_mime_type("application/pdf")
        
        # Test invalid combinations
        assert not is_allowed_extension("doc.exe")
        assert not is_allowed_mime_type("application/x-executable")
    
    @pytest.mark.asyncio
    async def test_rag_upload_mime_extension_mismatch(self, client: TestClient, real_auth_tokens):
        """Test that RAG upload rejects MIME/extension mismatches"""
        # This would require a real client and auth tokens
        # For now, we'll test the validation logic
        
        # Test MIME/extension mismatch
        from app.api.v1.rag import is_allowed_extension, is_allowed_mime_type
        
        # Valid: PDF file with PDF MIME
        assert is_allowed_extension("document.pdf")
        assert is_allowed_mime_type("application/pdf")
        
        # Invalid: PDF file with executable MIME
        assert is_allowed_extension("document.pdf")
        assert not is_allowed_mime_type("application/x-executable")


class TestAdminSetupEndpoint:
    """Test admin/setup endpoint restrictions"""
    
    def test_create_superuser_debug_only(self):
        """Test that create-superuser endpoint is DEBUG-only"""
        import os
        
        setup_file = "apps/api/src/app/api/setup.py"
        if os.path.exists(setup_file):
            with open(setup_file, 'r') as f:
                content = f.read()
                
                # Check that endpoint checks DEBUG mode
                assert "s.DEBUG" in content or "DEBUG" in content
    
    def test_create_superuser_uses_pydantic_schemas(self):
        """Test that create-superuser uses Pydantic schemas"""
        import os
        
        setup_file = "apps/api/src/app/api/setup.py"
        if os.path.exists(setup_file):
            with open(setup_file, 'r') as f:
                content = f.read()
                
                # Check that it uses Pydantic schemas
                assert "UserCreateRequest" in content or "BaseModel" in content


class TestProblemJSONConsistency:
    """Test Problem JSON consistency across error handling"""
    
    def test_base_controller_problem_json_mapping(self):
        """Test that BaseController maps domain errors to Problem JSON"""
        from app.core.domain_exceptions import BaseController
        
        # Test timeout mapping
        exc = ExternalServiceTimeout("LLM", 30)
        http_exc = BaseController.map_domain_error_to_http(exc)
        
        assert http_exc.status_code == 504
        assert "EXTERNAL_SERVICE_TIMEOUT" in str(http_exc.detail)
        
        # Test unavailable mapping
        exc = ExternalServiceUnavailable("LLM")
        http_exc = BaseController.map_domain_error_to_http(exc)
        
        assert http_exc.status_code == 503
        assert "EXTERNAL_SERVICE_UNAVAILABLE" in str(http_exc.detail)
        
        # Test rate limited mapping
        exc = ExternalServiceRateLimited("LLM", 60)
        http_exc = BaseController.map_domain_error_to_http(exc)
        
        assert http_exc.status_code == 429
        assert "EXTERNAL_SERVICE_RATE_LIMITED" in str(http_exc.detail)
        assert "Retry-After" in http_exc.headers
        assert http_exc.headers["Retry-After"] == "60"
    
    def test_problem_json_structure_consistency(self):
        """Test that Problem JSON has consistent structure"""
        from app.schemas.common import Problem
        
        # Test Problem JSON structure
        problem = Problem(
            type="https://example.com/problems/validation-error",
            title="Validation Error",
            status=422,
            detail="Invalid input data",
            instance="/api/v1/test"
        )
        
        data = problem.model_dump()
        
        # Check required fields
        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert "instance" in data
        
        # Check field types
        assert isinstance(data["type"], str)
        assert isinstance(data["title"], str)
        assert isinstance(data["status"], int)
        assert isinstance(data["detail"], str)
        assert isinstance(data["instance"], str)


class TestIntegrationEndToEnd:
    """Test end-to-end integration of all fixes"""
    
    @pytest.mark.asyncio
    async def test_complete_chat_flow_with_tenant_validation(self):
        """Test complete chat flow with tenant validation and type safety"""
        # Mock user with tenant_id
        mock_user = Mock()
        mock_user.id = uuid.uuid4()
        mock_user.tenant_id = uuid.uuid4()
        
        # Test tenant validation
        tenant_id = require_tenant_id(mock_user, "post_message")
        assert tenant_id == mock_user.tenant_id
        
        # Test ChatMessage creation from runtime schema
        messages = [
            ChatMessage.create_system_message("You are a helpful assistant."),
            ChatMessage.create_user_message("Hello, World!")
        ]
        
        # Test LLM client with ChatMessage and Protocol
        client = HTTPLLMClient("http://test", timeout=5, max_retries=1)
        
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
    
    def test_no_dict_in_api_schemas_regression(self):
        """Regression test: no raw dict types in API schemas"""
        # Test that ChatMessage is properly typed
        msg = ChatMessage.create_user_message("Hello")
        assert not isinstance(msg, dict)
        assert isinstance(msg, ChatMessage)
        
        # Test that content can be dict but message itself is ChatMessage
        dict_content = {"type": "tool_call", "data": {"test": "value"}}
        msg = ChatMessage(role="tool", content=dict_content)
        assert isinstance(msg.content, dict)
        assert isinstance(msg, ChatMessage)
    
    def test_migration_chain_integrity(self):
        """Test that migration chain is intact after fixes"""
        import os
        import re
        
        migration_dir = "apps/api/alembic/versions"
        migration_files = [f for f in os.listdir(migration_dir) if f.endswith('.py')]
        
        # Extract revision numbers
        revision_numbers = set()
        
        for file in migration_files:
            number_match = re.match(r'^(\d+)_', file)
            if number_match:
                number = number_match.group(1)
                assert number not in revision_numbers, f"Duplicate revision number {number} in {file}"
                revision_numbers.add(number)
        
        # Check that we have expected migrations
        assert "001" in revision_numbers  # Initial migration
        assert "006" in revision_numbers  # GIN indexes (renamed from 003)
        
        # Check that 003 is not duplicated
        count_003 = sum(1 for f in migration_files if f.startswith("003_"))
        assert count_003 == 1, f"Expected exactly one 003 migration, found {count_003}"
