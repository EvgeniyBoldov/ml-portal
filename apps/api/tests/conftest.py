"""
Pytest configuration for API tests
"""
import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock SQLAlchemy async session"""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
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


# Runtime refactor specific fixtures
@pytest.fixture
def mock_llm_client():
    """Mock LLM client for runtime tests"""
    client = AsyncMock()
    
    # Mock chat response
    client.chat.return_value = '{"content": "Mock response", "tool_calls": []}'
    
    # Mock streaming
    async def mock_stream(*args, **kwargs):
        yield "Mock streaming response"
    
    client.chat_stream = mock_stream
    return client


@pytest.fixture
def mock_run_store():
    """Mock RunStore for runtime tests"""
    store = AsyncMock()
    store.start_run = AsyncMock(return_value=uuid4())
    store.add_step = AsyncMock()
    store.finish_run = AsyncMock()
    return store


@pytest.fixture
def sample_chat_id() -> str:
    """Sample chat ID for runtime tests"""
    return str(uuid4())


@pytest.fixture
def sample_user_id() -> str:
    """Sample user ID for runtime tests"""
    return str(uuid4())
