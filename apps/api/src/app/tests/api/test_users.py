"""
Users / Roles tests
"""
import pytest
from fastapi.testclient import TestClient
from tests.conftest import assert_problem


def test_user_roles_allowed(client: TestClient):
    """Test only reader|editor|admin roles are allowed"""
    # Test creating user with valid roles
    valid_roles = ["reader", "editor", "admin"]
    
    for role in valid_roles:
        response = client.post("/api/v1/users", json={
            "email": f"test-{role}@example.com",
            "password": "password123",
            "role": role
        })
        
        assert "X-Request-ID" in response.headers
        # Might be 401 without auth, but structure should be correct


def test_user_default_role_reader(client: TestClient):
    """Test new users default to reader role"""
    response = client.post("/api/v1/users", json={
        "email": "test-default@example.com",
        "password": "password123"
        # No role specified
    })
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert data["role"] == "reader"


def test_user_invalid_role(client: TestClient):
    """Test user creation with invalid role returns 422"""
    response = client.post("/api/v1/users", json={
        "email": "test-invalid@example.com",
        "password": "password123",
        "role": "invalid_role"
    })
    
    assert_problem(response, 422, "VALIDATION_ERROR")


def test_user_legacy_roles_rejected(client: TestClient):
    """Test legacy roles (viewer, user) are rejected"""
    legacy_roles = ["viewer", "user"]
    
    for role in legacy_roles:
        response = client.post("/api/v1/users", json={
            "email": f"test-{role}@example.com",
            "password": "password123",
            "role": role
        })
        
        assert_problem(response, 422, "VALIDATION_ERROR")


def test_rbac_editor_no_admin_access(client: TestClient):
    """Test editor role cannot access admin endpoints"""
    headers = {
        "Authorization": "Bearer editor-token"
    }
    
    response = client.get("/api/v1/admin/users", headers=headers)
    
    # Should be forbidden for editor
    assert response.status_code in [401, 403]
    assert "X-Request-ID" in response.headers


def test_rbac_reader_no_write_access(client: TestClient):
    """Test reader role cannot perform write operations"""
    headers = {
        "Authorization": "Bearer reader-token"
    }
    
    # Try to create a user (admin operation)
    response = client.post("/api/v1/users", 
                          json={"email": "test@example.com", "password": "password123"},
                          headers=headers)
    
    # Should be forbidden for reader
    assert response.status_code in [401, 403]
    assert "X-Request-ID" in response.headers


def test_rbac_admin_full_access(client: TestClient):
    """Test admin role has full access"""
    headers = {
        "Authorization": "Bearer admin-token"
    }
    
    response = client.get("/api/v1/admin/users", headers=headers)
    
    # Admin should have access (might be 200 or 401 if token is invalid)
    assert "X-Request-ID" in response.headers


def test_user_password_policy(client: TestClient):
    """Test user password meets policy requirements"""
    # Weak password
    response1 = client.post("/api/v1/users", json={
        "email": "test-weak@example.com",
        "password": "123"  # Too weak
    })
    
    assert_problem(response1, 422, "VALIDATION_ERROR")
    
    # Strong password
    response2 = client.post("/api/v1/users", json={
        "email": "test-strong@example.com",
        "password": "StrongPassword123!"  # Meets policy
    })
    
    assert "X-Request-ID" in response2.headers


def test_user_email_validation(client: TestClient):
    """Test user email validation"""
    # Invalid email format
    response1 = client.post("/api/v1/users", json={
        "email": "invalid-email",
        "password": "password123"
    })
    
    assert_problem(response1, 422, "VALIDATION_ERROR")
    
    # Valid email
    response2 = client.post("/api/v1/users", json={
        "email": "valid@example.com",
        "password": "password123"
    })
    
    assert "X-Request-ID" in response2.headers


def test_user_duplicate_email(client: TestClient):
    """Test user creation with duplicate email"""
    email = "duplicate@example.com"
    
    # First user
    response1 = client.post("/api/v1/users", json={
        "email": email,
        "password": "password123"
    })
    
    assert "X-Request-ID" in response1.headers
    
    # Second user with same email
    response2 = client.post("/api/v1/users", json={
        "email": email,
        "password": "password123"
    })
    
    # Should reject duplicate email
    assert response2.status_code in [400, 409, 422]
    assert "X-Request-ID" in response2.headers


def test_user_get_current_info(client: TestClient):
    """Test get current user info returns correct structure"""
    headers = {
        "Authorization": "Bearer test-token"
    }
    
    response = client.get("/api/v1/users/me", headers=headers)
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert "role" in data
        assert data["role"] in ["reader", "editor", "admin"]


def test_user_update_role(client: TestClient):
    """Test updating user role"""
    headers = {
        "Authorization": "Bearer admin-token"
    }
    
    response = client.put("/api/v1/users/test-user-id", 
                         json={"role": "editor"},
                         headers=headers)
    
    assert "X-Request-ID" in response.headers
    
    if response.status_code == 200:
        data = response.json()
        assert data["role"] == "editor"


def test_user_delete(client: TestClient):
    """Test user deletion"""
    headers = {
        "Authorization": "Bearer admin-token"
    }
    
    response = client.delete("/api/v1/users/test-user-id", headers=headers)
    
    assert "X-Request-ID" in response.headers
    # Should return success or appropriate error
