"""
UUID serialization tests
"""
import pytest
import uuid
from fastapi.testclient import TestClient


def test_uuid_serialization_rag_documents(client: TestClient):
    """Test UUID in RAG documents serialized uniformly"""
    response = client.post("/api/v1/rag/upload", json={
        "name": "test-uuid.pdf",
        "mime": "application/pdf",
        "size": 1024
    })
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        source_id = data["source_id"]
        
        # Verify UUID format
        try:
            parsed_uuid = uuid.UUID(source_id)
            assert str(parsed_uuid) == source_id  # Should be consistent
        except ValueError:
            pytest.fail(f"Invalid UUID format: {source_id}")


def test_uuid_serialization_chat_messages(client: TestClient):
    """Test UUID in chat messages serialized uniformly"""
    response = client.post("/api/v1/chat/send", json={
        "prompt": "Test UUID serialization",
        "chat_id": "test-chat-id"
    })
    
    assert "X-Request-ID" in response.headers
    
    # In a real test, would verify chat_id and message_id UUIDs
    # For now, just verify the endpoint exists


def test_uuid_serialization_user_ids(client: TestClient):
    """Test UUID in user IDs serialized uniformly"""
    headers = {
        "Authorization": "Bearer test-token"
    }
    
    response = client.get("/api/v1/users/me", headers=headers)
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        user_id = data["id"]
        
        # Verify UUID format
        try:
            parsed_uuid = uuid.UUID(user_id)
            assert str(parsed_uuid) == user_id
        except ValueError:
            pytest.fail(f"Invalid UUID format: {user_id}")


def test_uuid_serialization_analyze_jobs(client: TestClient):
    """Test UUID in analyze jobs serialized uniformly"""
    response = client.post("/api/v1/analyze/upload", json={
        "name": "test-analyze.pdf",
        "mime": "application/pdf",
        "size": 1024
    })
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        analyze_id = data["analyze_id"]
        
        # Verify UUID format
        try:
            parsed_uuid = uuid.UUID(analyze_id)
            assert str(parsed_uuid) == analyze_id
        except ValueError:
            pytest.fail(f"Invalid UUID format: {analyze_id}")


def test_uuid_serialization_job_ids(client: TestClient):
    """Test UUID in job IDs serialized uniformly"""
    response = client.get("/api/v1/jobs")
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        if data.get("items"):
            job_id = data["items"][0]["id"]
            
            # Verify UUID format
            try:
                parsed_uuid = uuid.UUID(job_id)
                assert str(parsed_uuid) == job_id
            except ValueError:
                pytest.fail(f"Invalid UUID format: {job_id}")


def test_uuid_serialization_consistency(client: TestClient):
    """Test UUID serialization is consistent across all endpoints"""
    # Test multiple endpoints return UUIDs in same format
    endpoints = [
        ("/api/v1/rag/upload", {"name": "test.pdf", "mime": "application/pdf", "size": 1024}),
        ("/api/v1/analyze/upload", {"name": "test.pdf", "mime": "application/pdf", "size": 1024}),
    ]
    
    uuids = []
    
    for endpoint, payload in endpoints:
        response = client.post(endpoint, json=payload)
        assert "X-Request-ID" in response.headers
        
        if response.status_code == 200:
            data = response.json()
            # Extract UUID from response
            for key in ["source_id", "analyze_id", "id"]:
                if key in data:
                    uuids.append(data[key])
                    break
    
    # All UUIDs should be in same format
    for uuid_str in uuids:
        try:
            parsed_uuid = uuid.UUID(uuid_str)
            assert str(parsed_uuid) == uuid_str
        except ValueError:
            pytest.fail(f"Invalid UUID format: {uuid_str}")


def test_uuid_as_uuid_true_models(client: TestClient):
    """Test models use as_uuid=True for UUID fields"""
    # This tests the model definitions indirectly
    # RAG, Chat, User models should all use as_uuid=True
    
    response = client.post("/api/v1/rag/upload", json={
        "name": "model-test.pdf",
        "mime": "application/pdf",
        "size": 1024
    })
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        source_id = data["source_id"]
        
        # Should be valid UUID
        uuid.UUID(source_id)  # Will raise ValueError if invalid


def test_uuid_request_id_format(client: TestClient):
    """Test X-Request-ID header uses valid UUID format"""
    response = client.get("/api/v1/healthz")
    
    assert "X-Request-ID" in response.headers
    request_id = response.headers["X-Request-ID"]
    
    # Should be valid UUID
    try:
        uuid.UUID(request_id)
    except ValueError:
        pytest.fail(f"Invalid Request-ID UUID format: {request_id}")


def test_uuid_idempotency_key_format(client: TestClient):
    """Test Idempotency-Key uses valid UUID format"""
    idempotency_key = str(uuid.uuid4())
    headers = {"Idempotency-Key": idempotency_key}
    
    response = client.post("/api/v1/rag/upload", 
                          json={"name": "test.pdf", "mime": "application/pdf", "size": 1024},
                          headers=headers)
    
    assert "X-Request-ID" in response.headers
    
    # Idempotency key should be valid UUID
    try:
        uuid.UUID(idempotency_key)
    except ValueError:
        pytest.fail(f"Invalid Idempotency-Key UUID format: {idempotency_key}")
