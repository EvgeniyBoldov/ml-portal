import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.main import app
from app.core.security import hash_password
from app.repositories.users_repo import UsersRepo
from app.schemas.admin import UserRole


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_user(session: Session):
    """Create admin user for testing."""
    repo = UsersRepo(session)
    user = repo.create_user(
        login="admin",
        password_hash=hash_password("admin123456"),
        role="admin",
        email="admin@test.com",
        is_active=True
    )
    return user


@pytest.fixture
def editor_user(session: Session):
    """Create editor user for testing."""
    repo = UsersRepo(session)
    user = repo.create_user(
        login="editor",
        password_hash=hash_password("editor123456"),
        role="editor",
        email="editor@test.com",
        is_active=True
    )
    return user


@pytest.fixture
def reader_user(session: Session):
    """Create reader user for testing."""
    repo = UsersRepo(session)
    user = repo.create_user(
        login="reader",
        password_hash=hash_password("reader123456"),
        role="reader",
        email="reader@test.com",
        is_active=True
    )
    return user


def get_auth_headers(client: TestClient, login: str, password: str):
    """Get authorization headers for a user."""
    response = client.post("/api/auth/login", json={"login": login, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestRBAC:
    """Test RBAC functionality."""
    
    def test_admin_can_access_all_endpoints(self, client: TestClient, admin_user):
        """Test that admin can access all endpoints."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        # Test admin endpoints
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 200
        
        # Test RAG endpoints
        response = client.get("/api/rag/", headers=headers)
        assert response.status_code == 200
        
        response = client.get("/api/rag/stats", headers=headers)
        assert response.status_code == 200
    
    def test_editor_can_access_rag_write_operations(self, client: TestClient, editor_user):
        """Test that editor can access RAG write operations."""
        headers = get_auth_headers(client, "editor", "editor123456")
        
        # Test RAG read operations
        response = client.get("/api/rag/", headers=headers)
        assert response.status_code == 200
        
        response = client.get("/api/rag/stats", headers=headers)
        assert response.status_code == 200
        
        # Test RAG search
        response = client.post("/api/rag/search", json={"query": "test"}, headers=headers)
        assert response.status_code == 200
    
    def test_editor_cannot_access_admin_endpoints(self, client: TestClient, editor_user):
        """Test that editor cannot access admin endpoints."""
        headers = get_auth_headers(client, "editor", "editor123456")
        
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403
    
    def test_reader_can_access_read_operations(self, client: TestClient, reader_user):
        """Test that reader can access read operations."""
        headers = get_auth_headers(client, "reader", "reader123456")
        
        # Test RAG read operations
        response = client.get("/api/rag/", headers=headers)
        assert response.status_code == 200
        
        response = client.get("/api/rag/stats", headers=headers)
        assert response.status_code == 200
        
        # Test RAG search
        response = client.post("/api/rag/search", json={"query": "test"}, headers=headers)
        assert response.status_code == 200
    
    def test_reader_cannot_access_write_operations(self, client: TestClient, reader_user):
        """Test that reader cannot access write operations."""
        headers = get_auth_headers(client, "reader", "reader123456")
        
        # Test RAG upload (should fail)
        with open("test_file.txt", "w") as f:
            f.write("test content")
        
        try:
            with open("test_file.txt", "rb") as f:
                response = client.post("/api/rag/upload", files={"file": f}, headers=headers)
                assert response.status_code == 403
        finally:
            import os
            if os.path.exists("test_file.txt"):
                os.remove("test_file.txt")
    
    def test_reader_cannot_access_admin_endpoints(self, client: TestClient, reader_user):
        """Test that reader cannot access admin endpoints."""
        headers = get_auth_headers(client, "reader", "reader123456")
        
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403
    
    def test_inactive_user_cannot_access_anything(self, client: TestClient, session: Session):
        """Test that inactive user cannot access anything."""
        repo = UsersRepo(session)
        user = repo.create_user(
            login="inactive",
            password_hash=hash_password("inactive123456"),
            role="admin",
            is_active=False
        )
        
        headers = get_auth_headers(client, "inactive", "inactive123456")
        
        # Should get 401 for any endpoint
        response = client.get("/api/rag/", headers=headers)
        assert response.status_code == 401


class TestAdminAPI:
    """Test admin API functionality."""
    
    def test_create_user(self, client: TestClient, admin_user):
        """Test creating a new user."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        user_data = {
            "login": "newuser",
            "password": "newuser123456",
            "role": "reader",
            "email": "newuser@test.com"
        }
        
        response = client.post("/api/admin/users", json=user_data, headers=headers)
        assert response.status_code == 201
        
        data = response.json()
        assert data["login"] == "newuser"
        assert data["role"] == "reader"
        assert data["email"] == "newuser@test.com"
        assert data["is_active"] is True
    
    def test_list_users(self, client: TestClient, admin_user, editor_user, reader_user):
        """Test listing users."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] >= 3  # At least our test users
        assert len(data["users"]) >= 3
    
    def test_get_user(self, client: TestClient, admin_user, editor_user):
        """Test getting a specific user."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        response = client.get(f"/api/admin/users/{editor_user.id}", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == str(editor_user.id)
        assert data["login"] == "editor"
        assert data["role"] == "editor"
    
    def test_update_user(self, client: TestClient, admin_user, editor_user):
        """Test updating a user."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        update_data = {
            "role": "reader",
            "is_active": False
        }
        
        response = client.patch(f"/api/admin/users/{editor_user.id}", json=update_data, headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["role"] == "reader"
        assert data["is_active"] is False
    
    def test_reset_user_password(self, client: TestClient, admin_user, editor_user):
        """Test resetting user password."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        response = client.post(f"/api/admin/users/{editor_user.id}/password", json={}, headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "new_password" in data
        assert len(data["new_password"]) > 0
    
    def test_create_pat_token(self, client: TestClient, admin_user, editor_user):
        """Test creating a PAT token."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        token_data = {
            "name": "test-token",
            "scopes": ["api:read", "rag:read"]
        }
        
        response = client.post(f"/api/admin/users/{editor_user.id}/tokens", json=token_data, headers=headers)
        assert response.status_code == 201
        
        data = response.json()
        assert data["name"] == "test-token"
        assert "token_plain_once" in data
        assert data["scopes"] == ["api:read", "rag:read"]
    
    def test_list_user_tokens(self, client: TestClient, admin_user, editor_user):
        """Test listing user tokens."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        # Create a token first
        token_data = {"name": "test-token"}
        client.post(f"/api/admin/users/{editor_user.id}/tokens", json=token_data, headers=headers)
        
        response = client.get(f"/api/admin/users/{editor_user.id}/tokens", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] >= 1
        assert len(data["tokens"]) >= 1
    
    def test_audit_logs(self, client: TestClient, admin_user, editor_user):
        """Test audit logs functionality."""
        headers = get_auth_headers(client, "admin", "admin123456")
        
        # Perform some actions that should be logged
        client.patch(f"/api/admin/users/{editor_user.id}", json={"role": "reader"}, headers=headers)
        
        response = client.get("/api/admin/audit-logs", headers=headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] >= 1
        assert len(data["logs"]) >= 1
