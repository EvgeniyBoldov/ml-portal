"""
Глобальная конфигурация pytest для всех тестов.
"""
import os
import pytest
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

# Настройка переменных окружения для тестов
os.environ["TESTING"] = "true"
os.environ["DB_URL"] = "postgresql://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
os.environ["REDIS_URL"] = "redis://redis-test:6379"
os.environ["QDRANT_URL"] = "http://qdrant-test:6333"
os.environ["S3_ENDPOINT"] = "http://minio-test:9000"
os.environ["S3_ACCESS_KEY"] = "testadmin"
os.environ["S3_SECRET_KEY"] = "testadmin123"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_ALGORITHM"] = "HS256"

# Import fixtures from fixtures modules
from tests.fixtures.database import *
from tests.fixtures.migrations import *
from tests.fixtures.redis import *
from tests.fixtures.qdrant import *
from tests.fixtures.minio import *
from tests.fixtures.cleanup import *
from tests.fixtures.data import *


@pytest.fixture
def mock_db_session():
    """Мок для database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    """Мок для Redis клиента."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=False)
    redis.expire = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_s3_client():
    """Мок для S3 клиента."""
    s3 = AsyncMock()
    s3.put_object = AsyncMock(return_value={"ETag": '"test-etag"'})
    s3.get_object = AsyncMock(return_value={"Body": AsyncMock()})
    s3.delete_object = AsyncMock(return_value={})
    s3.head_object = AsyncMock(return_value={"ContentLength": 1024})
    return s3


@pytest.fixture
def mock_qdrant_client():
    """Мок для Qdrant клиента."""
    qdrant = AsyncMock()
    qdrant.upsert = AsyncMock(return_value={"operation_id": "test-op-id"})
    qdrant.search = AsyncMock(return_value={"result": []})
    qdrant.delete = AsyncMock(return_value={"operation_id": "test-op-id"})
    qdrant.get_collections = AsyncMock(return_value={"collections": []})
    qdrant.create_collection = AsyncMock(return_value={"result": True})
    return qdrant


@pytest.fixture
def sample_user_data():
    """Тестовые данные пользователя."""
    return {
        "id": 1,
        "email": "test@example.com",
        "username": "testuser",
        "is_active": True,
        "is_superuser": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def mock_llm_client():
    """Мок для LLM клиента."""
    from app.api.deps import get_llm_client_mock
    return get_llm_client_mock()


@pytest.fixture
def mock_emb_client():
    """Мок для Embeddings клиента."""
    from unittest.mock import AsyncMock
    mock_client = AsyncMock()
    mock_client.embed_texts.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_client.embed_query.return_value = [0.1, 0.2, 0.3]
    return mock_client


@pytest.fixture
def sample_chat_data():
    """Тестовые данные чата."""
    return {
        "id": 1,
        "user_id": 1,
        "title": "Test Chat",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_message_data():
    """Тестовые данные сообщения."""
    return {
        "id": 1,
        "chat_id": 1,
        "role": "user",
        "content": "Test message",
        "created_at": "2024-01-01T00:00:00Z"
    }
