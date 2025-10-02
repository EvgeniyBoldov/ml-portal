"""
Конфигурация для интеграционных тестов.
Настройка реальных сервисов: PostgreSQL, Redis, MinIO, Qdrant.
"""
import pytest
import asyncio
import uuid
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.db import get_async_session
from app.models.user import Base as UserBase, Users
from app.models.chat import Base as ChatBase
from app.models.rag import Base as RAGBase
from app.models.analyze import Base as AnalyzeBase
from app.models.tenant import Base as TenantBase, Tenants, UserTenants

# Remove custom event_loop fixture to avoid conflicts with pytest-asyncio
# pytest-asyncio will handle event loop management automatically


@pytest.fixture(scope="session")
async def test_db_engine():
    """Создает тестовую БД engine."""
    settings = get_settings()
    
    # Используем тестовую БД
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    
    engine = create_async_engine(
        test_db_url,
        echo=False,  # Отключаем SQL логи для тестов
        pool_pre_ping=True,
        pool_recycle=300,
    )
    
    # Создаем все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(UserBase.metadata.create_all)
        await conn.run_sync(ChatBase.metadata.create_all)
        await conn.run_sync(RAGBase.metadata.create_all)
        await conn.run_sync(AnalyzeBase.metadata.create_all)
    
    yield engine
    
    # Очищаем после тестов
    async with engine.begin() as conn:
        await conn.run_sync(UserBase.metadata.drop_all)
        await conn.run_sync(ChatBase.metadata.drop_all)
        await conn.run_sync(RAGBase.metadata.drop_all)
        await conn.run_sync(AnalyzeBase.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Создает тестовую сессию БД."""
    async_session = sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        # Откатываем все изменения после теста
        await session.rollback()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Создает асинхронный HTTP клиент для тестов."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def sync_client() -> Generator[TestClient, None, None]:
    """Создает синхронный HTTP клиент для тестов."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_tenant_id() -> str:
    """Создает тестовый tenant ID."""
    return str(uuid.uuid4())


@pytest.fixture
def test_user_id() -> str:
    """Создает тестовый user ID."""
    return str(uuid.uuid4())


@pytest.fixture
async def test_user(db_session: AsyncSession, test_tenant_id: str, test_user_id: str):
    """Создает тестового пользователя в БД."""
    from app.models.user import Users
    from app.models.tenant import Tenants, UserTenants
    from app.repositories.users_repo import UsersRepository
    
    # Create tenant first
    tenant = Tenants(
        id=test_tenant_id,
        name="test_tenant",
        is_active=True
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    
    # Create user
    user_data = {
        "id": test_user_id,
        "login": "integration_test",
        "email": "integration_test@example.com",
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",  # "testpassword"
        "is_active": True,
        "role": "reader"
    }
    
    user = Users(**user_data)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Link user to tenant using the new M2M model
    users_repo = UsersRepository(db_session)
    users_repo.add_to_tenant(user.id, tenant.id, is_default=True)
    await db_session.commit()
    
    yield user
    
    # Cleanup
    try:
        await db_session.delete(user)
        await db_session.delete(tenant)
        await db_session.commit()
    except:
        pass


@pytest.fixture
def auth_headers(test_user):
    """Создает заголовки авторизации для тестов."""
    # В реальном приложении здесь был бы JWT токен
    return {"Authorization": f"Bearer test-token-{test_user.id}"}


@pytest.fixture(scope="session")
def redis_client():
    """Создает Redis клиент для тестов."""
    import redis.asyncio as redis
    
    client = redis.from_url("redis://redis-test:6379", decode_responses=True)
    return client


@pytest.fixture
async def clean_redis(redis_client):
    """Очищает Redis перед каждым тестом."""
    await redis_client.flushdb()
    yield
    await redis_client.flushdb()


@pytest.fixture
def minio_client():
    """Создает MinIO клиент для тестов."""
    from minio import Minio
    
    client = Minio(
        "minio-test:9000",
        access_key="testadmin",
        secret_key="testadmin123",
        secure=False
    )
    
    # Создаем тестовые bucket'ы
    buckets = ["test-rag-documents", "test-artifacts", "test-uploads"]
    for bucket in buckets:
        try:
            client.make_bucket(bucket)
        except:
            pass  # Bucket уже существует
    
    return client


@pytest.fixture
async def clean_minio(minio_client):
    """Очищает MinIO перед каждым тестом."""
    buckets = ["test-rag-documents", "test-artifacts", "test-uploads"]
    
    # Очищаем все объекты в bucket'ах
    for bucket in buckets:
        try:
            objects = minio_client.list_objects(bucket, recursive=True)
            for obj in objects:
                minio_client.remove_object(bucket, obj.object_name)
        except:
            pass
    
    yield
    
    # Очищаем после теста
    for bucket in buckets:
        try:
            objects = minio_client.list_objects(bucket, recursive=True)
            for obj in objects:
                minio_client.remove_object(bucket, obj.object_name)
        except:
            pass


@pytest.fixture
def qdrant_client():
    """Создает Qdrant клиент для тестов."""
    from qdrant_client import QdrantClient
    
    client = QdrantClient(host="qdrant-test", port=6333)
    return client


@pytest.fixture
async def clean_qdrant(qdrant_client):
    """Очищает Qdrant перед каждым тестом."""
    # Удаляем все коллекции
    collections = qdrant_client.get_collections().collections
    for collection in collections:
        try:
            qdrant_client.delete_collection(collection.name)
        except:
            pass
    
    yield
    
    # Очищаем после теста
    collections = qdrant_client.get_collections().collections
    for collection in collections:
        try:
            qdrant_client.delete_collection(collection.name)
        except:
            pass


# Маркеры для группировки тестов
pytestmark = pytest.mark.integration
