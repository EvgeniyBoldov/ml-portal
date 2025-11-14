"""
E2E Test Configuration
Тесты работают через HTTP API с токенами, как в продакшене
"""
import os
import pytest
import httpx
from typing import Dict, Optional, Generator
from uuid import uuid4


# Конфигурация из .env.dev
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


class APIClient:
    """HTTP-клиент для E2E-тестов"""
    
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token
        self.client = httpx.Client(timeout=30.0)
    
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def post(self, path: str, json: Optional[Dict] = None, **kwargs):
        headers = self._headers()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        return self.client.post(
            f"{self.base_url}{path}",
            json=json,
            headers=headers,
            **kwargs
        )
    
    def get(self, path: str, **kwargs):
        return self.client.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            **kwargs
        )
    
    def patch(self, path: str, json: Optional[Dict] = None, **kwargs):
        return self.client.patch(
            f"{self.base_url}{path}",
            json=json,
            headers=self._headers(),
            **kwargs
        )
    
    def put(self, path: str, json: Optional[Dict] = None, **kwargs):
        return self.client.put(
            f"{self.base_url}{path}",
            json=json,
            headers=self._headers(),
            **kwargs
        )
    
    def delete(self, path: str, **kwargs):
        return self.client.delete(
            f"{self.base_url}{path}",
            headers=self._headers(),
            **kwargs
        )
    
    def close(self):
        self.client.close()


@pytest.fixture(scope="session")
def admin_token() -> str:
    """Получить токен администратора"""
    client = APIClient(API_BASE_URL)
    
    # Логин
    response = client.post("/auth/login", json={
        "login": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    token = data.get("access_token")
    assert token, "No access_token in response"
    
    client.close()
    return token


@pytest.fixture
def admin_client(admin_token: str) -> Generator[APIClient, None, None]:
    """HTTP-клиент с токеном администратора"""
    client = APIClient(API_BASE_URL, admin_token)
    yield client
    client.close()


@pytest.fixture
def test_tenant(admin_client: APIClient) -> Generator[Dict, None, None]:
    """Создать тестовый тенант"""
    tenant_name = f"test_tenant_{uuid4().hex[:8]}"
    
    response = admin_client.post("/tenants", json={
        "name": tenant_name,
        "description": "E2E test tenant"
    })
    
    assert response.status_code == 200, f"Failed to create tenant: {response.text}"
    tenant = response.json()
    
    yield tenant
    
    # Cleanup
    try:
        admin_client.delete(f"/tenants/{tenant['id']}")
    except Exception as e:
        print(f"Failed to cleanup tenant: {e}")


@pytest.fixture
def test_user(admin_client: APIClient, test_tenant: Dict) -> Generator[Dict, None, None]:
    """Создать тестового пользователя"""
    user_login = f"test_{uuid4().hex[:8]}"
    user_email = f"{user_login}@example.com"
    
    response = admin_client.post("/admin/users", json={
        "login": user_login,
        "email": user_email,
        "password": "test123",
        "tenant_ids": [test_tenant["id"]],
        "is_admin": False
    })
    
    assert response.status_code == 200, f"Failed to create user: {response.text}"
    data = response.json()
    user = data.get("user", data)  # API возвращает {"user": {...}}
    
    yield user
    
    # Cleanup
    try:
        admin_client.delete(f"/admin/users/{user['id']}")
    except Exception as e:
        print(f"Failed to cleanup user: {e}")


@pytest.fixture
def user_client(test_user: Dict) -> Generator[APIClient, None, None]:
    """HTTP-клиент с токеном тестового пользователя"""
    client = APIClient(API_BASE_URL)
    
    # Логин
    response = client.post("/auth/login", json={
        "login": test_user["email"],
        "password": "test123"
    })
    
    assert response.status_code == 200, f"User login failed: {response.text}"
    data = response.json()
    token = data.get("access_token")
    assert token, "No access_token in response"
    
    client.token = token
    yield client
    client.close()
