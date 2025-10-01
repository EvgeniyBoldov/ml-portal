"""
Test configuration and shared fixtures
"""
import asyncio
import pytest
import uuid
from typing import AsyncGenerator
from httpx import AsyncClient
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from app.main import app
from app.core.config import get_settings
from app.core.db import get_async_session


@pytest.fixture(scope="session", autouse=True)
def mock_redis_globally():
    """Mock Redis globally for all tests"""
    from unittest.mock import Mock, AsyncMock
    
    # Mock sync Redis
    mock_sync_redis = Mock()
    mock_sync_redis.set.return_value = True
    mock_sync_redis.get.return_value = None
    mock_sync_redis.delete.return_value = 1
    mock_sync_redis.keys.return_value = []
    mock_sync_redis.exists.return_value = False
    mock_sync_redis.expire.return_value = True
    mock_sync_redis.incr.return_value = 1
    
    # Mock async Redis
    mock_async_redis = AsyncMock()
    mock_async_redis.set.return_value = True
    mock_async_redis.get.return_value = None
    mock_async_redis.delete.return_value = 1
    mock_async_redis.keys.return_value = []
    mock_async_redis.exists.return_value = False
    mock_async_redis.expire.return_value = True
    mock_async_redis.incr.return_value = 1
    
    with patch('app.core.redis.get_sync_redis', return_value=mock_sync_redis), \
         patch('app.core.redis.get_async_redis', return_value=mock_async_redis):
        yield


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with lifespan"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Database session for tests"""
    # Create test engine
    s = get_settings()
    engine = create_async_engine(
        s.ASYNC_DB_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    # Create session factory
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_factory() as session:
        yield session


@pytest.fixture
def redis():
    """Redis client with cleanup"""
    from unittest.mock import Mock
    
    # Mock Redis client to avoid connection issues in tests
    mock_redis = Mock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None
    mock_redis.delete.return_value = 1
    mock_redis.keys.return_value = []
    mock_redis.exists.return_value = False
    mock_redis.expire.return_value = True
    mock_redis.incr.return_value = 1
    
    return mock_redis


@pytest.fixture
async def async_redis():
    """Async Redis client with cleanup"""
    from unittest.mock import AsyncMock
    
    # Mock async Redis client to avoid connection issues in tests
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None
    mock_redis.delete.return_value = 1
    mock_redis.keys.return_value = []
    mock_redis.exists.return_value = False
    mock_redis.expire.return_value = True
    mock_redis.incr.return_value = 1
    
    return mock_redis


@pytest.fixture
def minio_bucket():
    """MinIO bucket for tests"""
    from app.adapters.s3_client import S3Manager
    
    s3_manager = S3Manager()
    test_bucket = f"test-{uuid.uuid4().hex[:8]}"
    
    # Create test bucket
    s3_manager.ensure_bucket(test_bucket)
    
    yield test_bucket
    
    # Cleanup would go here if needed
    # (MinIO test container is ephemeral)


def assert_problem(response, expected_status: int, expected_code: str = None):
    """Helper to assert Problem JSON format"""
    assert response.status_code == expected_status
    assert response.headers.get("content-type") == "application/problem+json"
    
    data = response.json()
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert data["status"] == expected_status
    assert "detail" in data
    assert "trace_id" in data
    
    # Check X-Request-ID header matches trace_id
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id == data["trace_id"]
    
    if expected_code:
        assert "code" in data
        assert data["code"] == expected_code


@pytest.fixture
def auth_headers():
    """Mock auth headers for tests"""
    return {
        "Authorization": "Bearer test-token",
        "X-Request-ID": str(uuid.uuid4())
    }


@pytest.fixture
def idempotency_key():
    """Generate idempotency key for tests"""
    return str(uuid.uuid4())


@pytest.fixture
def auth_tokens(client):
    """Get access and refresh tokens through /auth/login"""
    # Mock user data for testing
    login_data = {
        "email": "test@example.com",
        "password": "testpassword123"
    }
    
    # Mock the authentication to return tokens
    with patch('app.services.users_service_enhanced.UsersService.authenticate_user') as mock_auth:
        from unittest.mock import Mock
        mock_user = Mock()
        mock_user.id = "test-user-id"
        mock_user.role = "editor"
        mock_user.login = "test@example.com"
        mock_user.fio = "Test User"
        mock_auth.return_value = mock_user
        
        response = client.post("/api/v1/auth/login", json=login_data)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "user": data["user"]
            }
        else:
            # Return mock tokens if login fails
            return {
                "access_token": "mock-access-token",
                "refresh_token": "mock-refresh-token",
                "user": {"id": "test-user-id", "role": "editor"}
            }


@pytest.fixture
def tenant_headers():
    """Headers for tenant testing"""
    return {
        "X-Tenant-Id": "test-tenant",
        "X-Request-ID": str(uuid.uuid4())
    }


@pytest.fixture
async def real_auth_tokens(client, async_db_session):
    """Get real access and refresh tokens by creating a test user (for future use)"""
    # This fixture creates a real test user in the database
    # and returns real tokens - useful for integration tests
    
    from app.repositories.users_repo_enhanced import UsersRepository
    from app.services.users_service_enhanced import UsersService
    from app.core.security import encode_jwt
    from datetime import datetime, timedelta
    
    # Create test user
    users_repo = UsersRepository(async_db_session)
    users_service = UsersService(users_repo)
    
    test_email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    test_password = "TestPassword123!"
    
    try:
        # Create user
        user = users_service.create_user(
            email=test_email,
            password=test_password,
            role="editor",
            fio="Test User"
        )
        
        # Generate real tokens
        access_payload = {
            "sub": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(minutes=15)
        }
        access_token = encode_jwt(access_payload, ttl_seconds=15*60)
        
        refresh_payload = {
            "sub": str(user.id),
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(days=30)
        }
        refresh_token = encode_jwt(refresh_payload, ttl_seconds=30*24*3600)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": str(user.id),
                "role": user.role,
                "login": user.login,
                "fio": user.fio
            },
            "email": test_email,
            "password": test_password
        }
        
    except Exception as e:
        # Fallback to mock tokens if user creation fails
        print(f"Failed to create real test user: {e}")
        return {
            "access_token": "mock-access-token",
            "refresh_token": "mock-refresh-token",
            "user": {"id": "test-user-id", "role": "editor"},
            "email": "test@example.com",
            "password": "testpassword123"
        }
