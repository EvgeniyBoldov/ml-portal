"""
Unit tests for IdempotencyService
"""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.idempotency_service import IdempotencyService


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

