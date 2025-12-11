"""
Pytest configuration for API tests
"""
import pytest
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock SQLAlchemy async session"""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client"""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def sample_tenant_id() -> str:
    """Sample tenant ID for tests"""
    return str(uuid4())


@pytest.fixture
def sample_doc_id() -> str:
    """Sample document ID for tests"""
    return str(uuid4())
