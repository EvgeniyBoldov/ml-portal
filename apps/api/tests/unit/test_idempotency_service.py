"""
Unit tests for IdempotencyService
"""
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import json

from app.services.idempotency_service import IdempotencyService
from app.core.exceptions import DuplicateError


class TestIdempotencyService:
    """Test IdempotencyService methods"""
    
    @pytest.fixture
    def mock_repo(self):
        """Mock idempotency repository"""
        repo = MagicMock()
        repo.create_idempotency_key = MagicMock()
        repo.get_by_key = MagicMock(return_value=None)
        repo.update_response = MagicMock()
        repo.delete_by_key = MagicMock()
        repo.cleanup_expired = MagicMock(return_value=0)
        return repo
    
    @pytest.fixture
    def idempotency_service(self, mock_repo):
        """Create IdempotencyService with mock repo"""
        return IdempotencyService(mock_repo)
    
    @pytest.fixture
    def sample_tenant_id(self):
        return uuid4()
    
    @pytest.fixture
    def sample_user_id(self):
        return uuid4()
    
    @pytest.fixture
    def sample_request_data(self):
        return {
            "method": "POST",
            "path": "/api/v1/rag/upload",
            "headers": {"content-type": "application/json"},
            "body": {"filename": "test.pdf"}
        }


class TestComputeRequestHash(TestIdempotencyService):
    """Test request hash computation"""
    
    def test_hash_is_deterministic(self, idempotency_service, sample_tenant_id, sample_user_id):
        """Same input should produce same hash"""
        hash1 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={"content-type": "application/json"},
            body={"key": "value"},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        hash2 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={"content-type": "application/json"},
            body={"key": "value"},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        assert hash1 == hash2
    
    def test_hash_differs_for_different_body(self, idempotency_service, sample_tenant_id, sample_user_id):
        """Different body should produce different hash"""
        hash1 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={},
            body={"key": "value1"},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        hash2 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={},
            body={"key": "value2"},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        assert hash1 != hash2
    
    def test_hash_differs_for_different_method(self, idempotency_service, sample_tenant_id, sample_user_id):
        """Different method should produce different hash"""
        hash1 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={},
            body={},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        hash2 = idempotency_service._compute_request_hash(
            method="PUT",
            path="/api/test",
            headers={},
            body={},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        assert hash1 != hash2
    
    def test_hash_ignores_authorization_header(self, idempotency_service, sample_tenant_id, sample_user_id):
        """Authorization header should be excluded from hash"""
        hash1 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={"authorization": "Bearer token1"},
            body={},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        hash2 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={"authorization": "Bearer token2"},
            body={},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        assert hash1 == hash2
    
    def test_hash_ignores_request_id_header(self, idempotency_service, sample_tenant_id, sample_user_id):
        """X-Request-ID header should be excluded from hash"""
        hash1 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={"x-request-id": "req-1"},
            body={},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        hash2 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={"x-request-id": "req-2"},
            body={},
            tenant_id=sample_tenant_id,
            user_id=sample_user_id
        )
        
        assert hash1 == hash2
    
    def test_hash_differs_for_different_tenant(self, idempotency_service, sample_user_id):
        """Different tenant should produce different hash"""
        hash1 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={},
            body={},
            tenant_id=uuid4(),
            user_id=sample_user_id
        )
        
        hash2 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={},
            body={},
            tenant_id=uuid4(),
            user_id=sample_user_id
        )
        
        assert hash1 != hash2
    
    def test_hash_handles_none_user_id(self, idempotency_service, sample_tenant_id):
        """Should handle None user_id"""
        hash1 = idempotency_service._compute_request_hash(
            method="POST",
            path="/api/test",
            headers={},
            body={},
            tenant_id=sample_tenant_id,
            user_id=None
        )
        
        assert hash1 is not None
        assert len(hash1) == 64  # SHA-256 hex


class TestCheckOrStoreResponse(TestIdempotencyService):
    """Test check_or_store_response method"""
    
    def test_new_request_returns_none_and_true(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """New request should return (None, True)"""
        mock_repo.create_idempotency_key.return_value = MagicMock()
        
        result, is_new = idempotency_service.check_or_store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=200,
            response_body={"id": "123"},
            response_headers={}
        )
        
        assert result is None
        assert is_new is True
        mock_repo.create_idempotency_key.assert_called_once()
    
    def test_duplicate_request_returns_cached_response(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Duplicate request should return cached response"""
        mock_repo.create_idempotency_key.side_effect = DuplicateError("Duplicate")
        
        cached_record = MagicMock()
        cached_record.response_status = 201
        cached_record.response_body = {"id": "existing"}
        cached_record.response_headers = {"x-custom": "header"}
        cached_record.ttl_at = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_repo.get_by_key.return_value = cached_record
        
        result, is_new = idempotency_service.check_or_store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=200,
            response_body={},
            response_headers={}
        )
        
        assert result is not None
        assert result["status"] == 201
        assert result["body"] == {"id": "existing"}
        assert result["idempotent_replay"] is True
        assert is_new is False
    
    def test_expired_cached_response_treated_as_new(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Expired cached response should be treated as new request"""
        mock_repo.create_idempotency_key.side_effect = DuplicateError("Duplicate")
        
        cached_record = MagicMock()
        cached_record.ttl_at = datetime.now(timezone.utc) - timedelta(hours=1)  # Expired
        mock_repo.get_by_key.return_value = cached_record
        
        result, is_new = idempotency_service.check_or_store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=200,
            response_body={},
            response_headers={}
        )
        
        assert result is None
        assert is_new is True
        mock_repo.delete_by_key.assert_called_once()
    
    def test_race_condition_record_deleted(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Race condition where record deleted between check and get"""
        mock_repo.create_idempotency_key.side_effect = DuplicateError("Duplicate")
        mock_repo.get_by_key.return_value = None  # Record was deleted
        
        result, is_new = idempotency_service.check_or_store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=200,
            response_body={},
            response_headers={}
        )
        
        assert result is None
        assert is_new is True


class TestStoreResponse(TestIdempotencyService):
    """Test store_response method"""
    
    def test_store_successful_response(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Should store 2xx response"""
        idempotency_service.store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=201,
            response_body={"id": "new"},
            response_headers={}
        )
        
        mock_repo.update_response.assert_called_once()
    
    def test_skip_error_response(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Should not store 4xx/5xx responses"""
        idempotency_service.store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=400,
            response_body={"error": "Bad request"},
            response_headers={}
        )
        
        mock_repo.update_response.assert_not_called()
    
    def test_skip_large_response(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Should not store responses larger than 256KB"""
        large_body = {"data": "x" * (300 * 1024)}  # > 256KB
        
        idempotency_service.store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=200,
            response_body=large_body,
            response_headers={}
        )
        
        mock_repo.update_response.assert_not_called()
    
    def test_fallback_to_create_on_update_failure(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Should try create if update fails"""
        mock_repo.update_response.side_effect = Exception("Update failed")
        mock_repo.create_idempotency_key.return_value = MagicMock()
        
        idempotency_service.store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=200,
            response_body={"id": "123"},
            response_headers={}
        )
        
        mock_repo.create_idempotency_key.assert_called_once()
    
    def test_ignore_duplicate_on_create_fallback(
        self, idempotency_service, mock_repo, sample_tenant_id, sample_user_id
    ):
        """Should ignore DuplicateError on create fallback"""
        mock_repo.update_response.side_effect = Exception("Update failed")
        mock_repo.create_idempotency_key.side_effect = DuplicateError("Duplicate")
        
        # Should not raise
        idempotency_service.store_response(
            tenant_id=sample_tenant_id,
            user_id=sample_user_id,
            key="idem-key-123",
            method="POST",
            path="/api/test",
            headers={},
            body={},
            response_status=200,
            response_body={"id": "123"},
            response_headers={}
        )


class TestCleanupExpiredKeys(TestIdempotencyService):
    """Test cleanup_expired_keys method"""
    
    def test_cleanup_returns_count(self, idempotency_service, mock_repo):
        """Should return count of deleted keys"""
        mock_repo.cleanup_expired.return_value = 5
        
        result = idempotency_service.cleanup_expired_keys()
        
        assert result == 5
        mock_repo.cleanup_expired.assert_called_once()
    
    def test_cleanup_returns_zero_when_none_expired(self, idempotency_service, mock_repo):
        """Should return 0 when no expired keys"""
        mock_repo.cleanup_expired.return_value = 0
        
        result = idempotency_service.cleanup_expired_keys()
        
        assert result == 0
