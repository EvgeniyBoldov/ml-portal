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

# Import migration fixtures
from app.tests.fixtures.migrations import test_db_engine, db_session, clean_db_session
from app.tests.fixtures.redis import redis_client, clean_redis
from app.tests.fixtures.qdrant import qdrant_client, clean_qdrant, test_collection_name


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Создает асинхронный HTTP клиент для тестов API."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def sync_client() -> Generator[TestClient, None, None]:
    """Создает синхронный HTTP клиент для тестов API."""
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
    from app.repositories.users_repo import AsyncUsersRepository
    
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
    users_repo = AsyncUsersRepository(db_session)
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
async def auth_headers(test_user):
    """Создает заголовки авторизации для тестов."""
    # В реальном приложении здесь был бы JWT токен
    user = await test_user
    return {"Authorization": f"Bearer test-token-{user.id}"}


@pytest.fixture
def simple_user_token():
    """Создает простой JWT токен для тестирования."""
    from app.core.security import create_access_token
    
    token = create_access_token(
        user_id="test-user-id",
        email="test@example.com",
        role="reader",
        tenant_ids=[],
        scopes=[]
    )
    return token


@pytest.fixture
def simple_admin_token():
    """Создает простой JWT токен для админа."""
    from app.core.security import create_access_token
    
    token = create_access_token(
        user_id="test-admin-id",
        email="admin@example.com",
        role="admin",
        tenant_ids=[],
        scopes=[]
    )
    return token