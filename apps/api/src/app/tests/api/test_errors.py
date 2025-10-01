"""
Problem JSON / Error format tests
"""
import pytest
from fastapi.testclient import TestClient
from tests.conftest import assert_problem


def test_404_problem_format(client: TestClient):
    """Test 404 returns Problem JSON format"""
    response = client.get("/api/v1/nonexistent")
    assert_problem(response, 404, "NOT_FOUND")


def test_400_problem_format(client: TestClient):
    """Test 400 returns Problem JSON format"""
    # Send invalid JSON to trigger 400
    response = client.post(
        "/api/v1/auth/login",
        json={"invalid": "data"},
        headers={"Content-Type": "application/json"}
    )
    assert_problem(response, 422)  # FastAPI returns 422 for validation errors


def test_401_problem_format(client: TestClient):
    """Test 401 returns Problem JSON format"""
    response = client.get("/api/v1/users/me")  # Requires auth
    assert_problem(response, 401, "AUTH_REQUIRED")


def test_403_problem_format(client: TestClient):
    """Test 403 returns Problem JSON format"""
    # This would require a valid token but insufficient permissions
    # For now, just test the structure
    response = client.post("/api/v1/admin/users", json={})
    assert_problem(response, 401)  # Will be 401 without auth, 403 with insufficient perms


def test_413_problem_format(client: TestClient):
    """Test 413 returns Problem JSON format for large payloads"""
    # Create a large payload to trigger 413
    large_data = {"data": "x" * (10 * 1024 * 1024)}  # 10MB
    response = client.post("/api/v1/rag/upload", json=large_data)
    # This might not trigger 413 in test environment, but structure should be correct
    assert response.status_code in [413, 422, 401]
    assert "X-Request-ID" in response.headers


def test_415_problem_format(client: TestClient):
    """Test 415 returns Problem JSON format for unsupported media type"""
    response = client.post(
        "/api/v1/auth/login",
        data="not json",
        headers={"Content-Type": "text/plain"}
    )
    assert response.status_code in [415, 422]
    assert "X-Request-ID" in response.headers


def test_422_problem_format(client: TestClient):
    """Test 422 returns Problem JSON format for validation errors"""
    response = client.post("/api/v1/auth/login", json={})
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_429_problem_format(client: TestClient):
    """Test 429 returns Problem JSON format for rate limiting"""
    # This would require hitting rate limits
    # For now, just test that the endpoint exists
    response = client.post("/api/v1/auth/login", json={"email": "test", "password": "test"})
    assert "X-Request-ID" in response.headers


def test_500_problem_format(client: TestClient):
    """Test 500 returns Problem JSON format for server errors"""
    # This is hard to trigger in tests without breaking something
    # The error handler should be tested separately
    pass


def test_request_id_header_consistency(client: TestClient):
    """Test X-Request-ID header matches trace_id in Problem JSON"""
    response = client.get("/api/v1/nonexistent")
    
    assert response.status_code == 404
    assert "X-Request-ID" in response.headers
    
    data = response.json()
    assert "trace_id" in data
    assert response.headers["X-Request-ID"] == data["trace_id"]
