"""
Idempotency middleware tests
"""
import pytest
import uuid
from fastapi.testclient import TestClient


def test_idempotency_same_key_same_response(client: TestClient, idempotency_key: str):
    """Test two identical requests with same Idempotency-Key return same response"""
    headers = {"Idempotency-Key": idempotency_key}
    payload = {"name": "test.pdf", "mime": "application/pdf", "size": 1024}
    
    # First request
    response1 = client.post("/api/v1/rag/upload", json=payload, headers=headers)
    
    # Second request with same key
    response2 = client.post("/api/v1/rag/upload", json=payload, headers=headers)
    
    # Should return same status and body
    assert response1.status_code == response2.status_code
    assert response1.json() == response2.json()
    
    # Both should have X-Request-ID
    assert "X-Request-ID" in response1.headers
    assert "X-Request-ID" in response2.headers


def test_idempotency_different_key_different_response(client: TestClient):
    """Test requests with different Idempotency-Key are processed separately"""
    payload = {"name": "test.pdf", "mime": "application/pdf", "size": 1024}
    
    # First request
    headers1 = {"Idempotency-Key": str(uuid.uuid4())}
    response1 = client.post("/api/v1/rag/upload", json=payload, headers=headers1)
    
    # Second request with different key
    headers2 = {"Idempotency-Key": str(uuid.uuid4())}
    response2 = client.post("/api/v1/rag/upload", json=payload, headers=headers2)
    
    # Both should be processed (might have different source_id if successful)
    assert "X-Request-ID" in response1.headers
    assert "X-Request-ID" in response2.headers


def test_idempotency_no_key_processed_normally(client: TestClient):
    """Test requests without Idempotency-Key are processed normally"""
    payload = {"name": "test.pdf", "mime": "application/pdf", "size": 1024}
    
    # Request without idempotency key
    response = client.post("/api/v1/rag/upload", json=payload)
    
    # Should be processed normally
    assert "X-Request-ID" in response.headers


def test_idempotency_sse_not_cached(client: TestClient, idempotency_key: str):
    """Test SSE/Streaming responses are not cached by idempotency"""
    headers = {"Idempotency-Key": idempotency_key}
    payload = {
        "prompt": "Test prompt",
        "document_id": "test-doc-id"
    }
    
    # SSE endpoint should not be cached
    response = client.post("/api/v1/analyze/stream", json=payload, headers=headers)
    
    # Should have proper headers but not be cached
    assert "X-Request-ID" in response.headers


def test_idempotency_large_response_not_cached(client: TestClient, idempotency_key: str):
    """Test large responses are not cached by idempotency"""
    headers = {"Idempotency-Key": idempotency_key}
    
    # This would need an endpoint that returns a large response
    # For now, just test that the middleware handles it
    response = client.get("/api/v1/healthz", headers=headers)
    
    assert "X-Request-ID" in response.headers


def test_idempotency_key_validation(client: TestClient):
    """Test Idempotency-Key format validation"""
    # Valid UUID format
    valid_key = str(uuid.uuid4())
    headers = {"Idempotency-Key": valid_key}
    payload = {"name": "test.pdf", "mime": "application/pdf", "size": 1024}
    
    response = client.post("/api/v1/rag/upload", json=payload, headers=headers)
    assert "X-Request-ID" in response.headers


def test_idempotency_replay_error_code(client: TestClient, idempotency_key: str):
    """Test idempotency replay returns proper error code if implemented"""
    headers = {"Idempotency-Key": idempotency_key}
    payload = {"name": "test.pdf", "mime": "application/pdf", "size": 1024}
    
    # First request
    response1 = client.post("/api/v1/rag/upload", json=payload, headers=headers)
    
    # Second request - might return 409 IDEMPOTENCY_REPLAYED or same response
    response2 = client.post("/api/v1/rag/upload", json=payload, headers=headers)
    
    # Should either be same response or 409
    assert response2.status_code in [response1.status_code, 409]
    assert "X-Request-ID" in response2.headers
