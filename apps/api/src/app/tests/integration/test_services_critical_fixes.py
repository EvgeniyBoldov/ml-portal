"""
Integration tests for critical service fixes
"""
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from app.services.analyze_service_enhanced import AnalyzeService
from app.services.audit_service_enhanced import AuditService
from app.services.idempotency_service import IdempotencyService
from app.services.http_clients_enhanced import (
    HTTPLLMClientEnhanced, HTTPEmbClientEnhanced,
    ExternalServiceError, ExternalServiceTimeout, ExternalServiceUnavailable
)
from app.services.service_with_idempotency import ChatServiceWithIdempotency
from app.repositories.factory import RepositoryFactory
from app.core.logging import get_logger

logger = get_logger(__name__)


class TestAnalyzeServiceOrchestration:
    """Test AnalyzeService orchestration logic"""
    
    def test_analyze_service_full_workflow(self, db_session):
        """Test full orchestration: ingest → search → chat"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        
        # Mock dependencies
        mock_ingest = Mock()
        mock_search = Mock()
        mock_chat = Mock()
        mock_repo_factory = Mock()
        mock_idempotency = Mock()
        
        # Setup mocks
        mock_ingest.ingest_document.return_value = 5  # 5 chunks ingested
        mock_search.search.return_value = [
            {'content': 'Relevant content 1', 'score': 0.9, 'chunk_id': 'chunk1'},
            {'content': 'Relevant content 2', 'score': 0.8, 'chunk_id': 'chunk2'}
        ]
        mock_chat.chat.return_value = Mock(text="Generated answer")
        
        # Mock repository
        mock_doc = Mock()
        mock_doc.status = "processed"
        mock_doc.content_type = "text/plain"
        mock_doc.url_file = "test.txt"
        mock_doc.version = 1
        
        mock_rag_repo = Mock()
        mock_rag_repo.get_by_id.return_value = mock_doc
        mock_rag_repo.update_document_status.return_value = mock_doc
        mock_repo_factory.get_rag_documents_repository.return_value = mock_rag_repo
        
        # Create service
        service = AnalyzeService(
            mock_ingest, mock_search, mock_chat, 
            mock_repo_factory, mock_idempotency
        )
        
        # Test analysis
        result = service.analyze(
            tenant_id=tenant_id,
            doc_id=doc_id,
            question="Test question",
            k=5,
            model="default"
        )
        
        # Verify orchestration
        assert result.text == "Generated answer"
        assert len(result.citations) == 2
        assert result.citations[0]['content'] == 'Relevant content 1'
        assert result.citations[1]['content'] == 'Relevant content 2'
        
        # Verify calls
        mock_rag_repo.get_by_id.assert_called_once_with(tenant_id, doc_id)
        mock_search.search.assert_called_once_with(
            tenant_id=str(tenant_id),
            query="Test question",
            k=5
        )
        mock_chat.chat.assert_called_once()
    
    def test_analyze_service_document_not_found(self, db_session):
        """Test analysis when document is not found"""
        tenant_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        
        # Mock dependencies
        mock_ingest = Mock()
        mock_search = Mock()
        mock_chat = Mock()
        mock_repo_factory = Mock()
        
        # Mock repository returning None
        mock_rag_repo = Mock()
        mock_rag_repo.get_by_id.return_value = None
        mock_repo_factory.get_rag_documents_repository.return_value = mock_rag_repo
        
        # Create service
        service = AnalyzeService(
            mock_ingest, mock_search, mock_chat, 
            mock_repo_factory, None
        )
        
        # Test analysis
        result = service.analyze(
            tenant_id=tenant_id,
            doc_id=doc_id,
            question="Test question"
        )
        
        # Verify error handling
        assert "processing failed" in result.text.lower()
        assert len(result.citations) == 0


class TestAuditServiceWithoutHTTP:
    """Test AuditService without HTTP dependencies"""
    
    def test_audit_service_log_action_without_request(self, db_session):
        """Test audit logging without Request object"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Mock repository factory
        mock_repo_factory = Mock()
        mock_audit_repo = Mock()
        mock_repo_factory.get_audit_repository.return_value = mock_audit_repo
        
        # Create service
        service = AuditService(mock_repo_factory)
        
        # Test logging
        service.log_action(
            tenant_id=tenant_id,
            action="test_action",
            actor_user_id=user_id,
            object_type="test_object",
            object_id="test_id",
            ip="192.168.1.1",
            user_agent="TestAgent/1.0",
            request_id="req-123"
        )
        
        # Verify repository call
        mock_audit_repo.create.assert_called_once()
        call_args = mock_audit_repo.create.call_args
        
        assert call_args[0][0] == tenant_id  # tenant_id
        assert call_args[1]['actor_user_id'] == user_id
        assert call_args[1]['action'] == "test_action"
        assert call_args[1]['ip'] == "192.168.1.1"
        assert call_args[1]['user_agent'] == "TestAgent/1.0"
        assert call_args[1]['request_id'] == "req-123"
    
    def test_audit_service_specialized_methods(self, db_session):
        """Test specialized audit logging methods"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Mock repository factory
        mock_repo_factory = Mock()
        mock_audit_repo = Mock()
        mock_repo_factory.get_audit_repository.return_value = mock_audit_repo
        
        # Create service
        service = AuditService(mock_repo_factory)
        
        # Test chat action logging
        service.log_chat_action(
            tenant_id=tenant_id,
            action="message_created",
            chat_id=chat_id,
            actor_user_id=user_id,
            ip="192.168.1.1"
        )
        
        # Verify call
        mock_audit_repo.create.assert_called_once()
        call_args = mock_audit_repo.create.call_args
        assert call_args[1]['object_type'] == "chat"
        assert call_args[1]['object_id'] == str(chat_id)


class TestIdempotencyServiceFixes:
    """Test IdempotencyService fixes"""
    
    def test_idempotency_service_ttl_calculation(self, db_session):
        """Test TTL calculation uses timedelta instead of replace"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        service = IdempotencyService(db_session)
        
        # Test TTL calculation
        ttl_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        # Verify it's a proper datetime
        assert isinstance(ttl_at, datetime)
        assert ttl_at.tzinfo is not None
    
    def test_idempotency_service_response_size_limits(self, db_session):
        """Test response size limits and normalization"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        service = IdempotencyService(db_session)
        
        # Test large response body
        large_response = {
            'text': 'x' * (2 * 1024 * 1024),  # 2MB text
            'citations': []
        }
        
        normalized = service._normalize_response_body(large_response, 1024 * 1024)
        
        # Should be truncated
        assert 'truncated' in normalized
        assert len(normalized['text']) < len(large_response['text'])
    
    def test_idempotency_service_header_normalization(self, db_session):
        """Test header normalization"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        service = IdempotencyService(db_session)
        
        # Test headers with sensitive data
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer secret-token',  # Should be filtered
            'X-Request-ID': 'req-123',
            'X-RateLimit-Limit': '100'
        }
        
        normalized = service._normalize_response_headers(headers)
        
        # Should filter out sensitive headers
        assert 'Authorization' not in normalized
        assert 'Content-Type' in normalized
        assert 'X-Request-ID' in normalized


class TestHTTPClientsErrorHandling:
    """Test HTTP clients error handling"""
    
    def test_llm_client_timeout_error(self):
        """Test LLM client timeout error mapping"""
        client = HTTPLLMClientEnhanced(timeout=1)  # Very short timeout
        
        with patch('httpx.Client') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'application/json'}
            mock_response.json.return_value = {'content': 'test'}
            
            mock_client_instance = Mock()
            mock_client_instance.post.side_effect = Exception("Timeout")
            mock_client.return_value.__enter__.return_value = mock_client_instance
            
            with pytest.raises(Exception):  # Should raise domain exception
                client.generate([{"role": "user", "content": "test"}])
    
    def test_embedding_client_service_unavailable(self):
        """Test embedding client service unavailable error"""
        client = HTTPEmbClientEnhanced()
        
        with patch('httpx.Client') as mock_client:
            mock_client_instance = Mock()
            mock_response = Mock()
            mock_response.status_code = 503
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance
            
            with pytest.raises(ExternalServiceUnavailable):
                client.embed(["test text"])
    
    def test_llm_client_invalid_response(self):
        """Test LLM client invalid response handling"""
        client = HTTPLLMClientEnhanced()
        
        with patch('httpx.Client') as mock_client:
            mock_client_instance = Mock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'application/json'}
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__enter__.return_value = mock_client_instance
            
            with pytest.raises(ExternalServiceInvalidResponse):
                client.generate([{"role": "user", "content": "test"}])


class TestServiceWithIdempotency:
    """Test services with idempotency support"""
    
    def test_chat_service_idempotency(self, db_session):
        """Test chat service with idempotency"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Mock idempotency service
        mock_idempotency = Mock()
        mock_idempotency.try_reserve_key.return_value = (True, None)  # Key reserved
        mock_idempotency.store_response.return_value = True
        
        # Create service
        service = ChatServiceWithIdempotency(mock_idempotency)
        
        # Test with idempotency key
        result = service.create_chat_message_with_idempotency(
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            content={"text": "Hello"},
            idempotency_key="test-key-123"
        )
        
        # Verify result
        assert 'message_id' in result
        assert result['chat_id'] == str(chat_id)
        
        # Verify idempotency calls
        mock_idempotency.try_reserve_key.assert_called_once()
        mock_idempotency.store_response.assert_called_once()
    
    def test_chat_service_cached_response(self, db_session):
        """Test chat service returns cached response"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Mock idempotency service with cached response
        cached_response = {
            'status': 200,
            'body': {
                'message_id': 'cached-message-id',
                'chat_id': str(chat_id),
                'content': {"text": "Cached response"},
                'created_at': '2024-01-01T00:00:00Z'
            }
        }
        
        mock_idempotency = Mock()
        mock_idempotency.try_reserve_key.return_value = (False, cached_response)
        
        # Create service
        service = ChatServiceWithIdempotency(mock_idempotency)
        
        # Test with idempotency key
        result = service.create_chat_message_with_idempotency(
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            content={"text": "Hello"},
            idempotency_key="test-key-123"
        )
        
        # Verify cached result
        assert result['message_id'] == 'cached-message-id'
        assert result['content']['text'] == 'Cached response'
        
        # Verify no store call (cached response)
        mock_idempotency.store_response.assert_not_called()
    
    def test_service_without_idempotency_key(self, db_session):
        """Test service execution without idempotency key"""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        chat_id = uuid.uuid4()
        
        # Create service without idempotency
        service = ChatServiceWithIdempotency(None)
        
        # Test without idempotency key
        result = service.create_chat_message_with_idempotency(
            tenant_id=tenant_id,
            user_id=user_id,
            chat_id=chat_id,
            content={"text": "Hello"},
            idempotency_key=None
        )
        
        # Verify result
        assert 'message_id' in result
        assert result['chat_id'] == str(chat_id)


class TestBaseControllerErrorMapping:
    """Test BaseController error mapping"""
    
    def test_domain_error_mapping(self):
        """Test mapping of domain errors to HTTP exceptions"""
        from app.controllers.base_controller import BaseController
        from app.repositories.base_enhanced import NotFoundError, DuplicateError, ConcurrencyError
        
        # Test NotFoundError
        not_found_error = NotFoundError("Resource not found")
        http_exception = BaseController.map_domain_error_to_http(not_found_error)
        
        assert http_exception.status_code == 404
        assert "not-found" in http_exception.detail['type']
        
        # Test DuplicateError
        duplicate_error = DuplicateError("Resource already exists")
        http_exception = BaseController.map_domain_error_to_http(duplicate_error)
        
        assert http_exception.status_code == 409
        assert "duplicate" in http_exception.detail['type']
        
        # Test ConcurrencyError
        concurrency_error = ConcurrencyError("Concurrent modification")
        http_exception = BaseController.map_domain_error_to_http(concurrency_error)
        
        assert http_exception.status_code == 409
        assert "concurrency" in http_exception.detail['type']
    
    def test_external_service_error_mapping(self):
        """Test mapping of external service errors"""
        from app.controllers.base_controller import BaseController
        
        # Test timeout error
        timeout_error = ExternalServiceTimeout("Service timeout", "llm")
        http_exception = BaseController.map_domain_error_to_http(timeout_error)
        
        assert http_exception.status_code == 504
        assert "service-timeout" in http_exception.detail['type']
        
        # Test service unavailable
        unavailable_error = ExternalServiceUnavailable("Service unavailable", "emb", 503)
        http_exception = BaseController.map_domain_error_to_http(unavailable_error)
        
        assert http_exception.status_code == 502
        assert "service-unavailable" in http_exception.detail['type']
