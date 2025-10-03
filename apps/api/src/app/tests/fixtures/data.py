"""
Фикстуры для генерации тестовых данных.
"""
import pytest
import uuid
from datetime import datetime


@pytest.fixture
def unique_tenant_name():
    """Генерирует уникальное имя tenant'а для тестов."""
    return f"test_tenant_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def unique_user_email():
    """Генерирует уникальный email пользователя для тестов."""
    return f"test_user_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture
def unique_chat_name():
    """Генерирует уникальное имя чата для тестов."""
    return f"test_chat_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_tenant_data(unique_tenant_name):
    """Создает данные для тестового tenant'а."""
    return {
        "id": uuid.uuid4(),
        "name": unique_tenant_name,
        "is_active": True,
    }


@pytest.fixture
def test_user_data(unique_user_email):
    """Создает данные для тестового пользователя."""
    return {
        "id": uuid.uuid4(),
        "email": unique_user_email,
        "hashed_password": "hashed_password_123",
        "is_active": True,
        "is_verified": True,
    }


@pytest.fixture
def test_chat_data(unique_chat_name):
    """Создает данные для тестового чата."""
    return {
        "id": uuid.uuid4(),
        "name": unique_chat_name,
        "user_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
    }
