"""
Enhanced test configuration for ML Portal
"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import uuid

# Add the app directory to Python path
sys.path.insert(0, '/app')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main_enhanced import app
from app.core.db import SessionLocal
from app.models.base import Base
from app.core.config import settings

# Test database URL - use PostgreSQL as per project rules
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Override the get_db dependency"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine"""
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(db_engine):
    """Create test database session"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    """Create test client with database session override"""
    from app.core.auth import get_current_user, require_user, require_admin
    from app.api.schemas.users import UserRole
    
    # Mock authentication for tests
    def mock_get_current_user():
        from app.core.auth import UserCtx
        return UserCtx(id="test-user-id", role="reader")
    
    def mock_require_user():
        from app.core.auth import UserCtx
        return UserCtx(id="test-user-id", role="reader")
    
    def mock_require_admin():
        from app.core.auth import UserCtx
        return UserCtx(id="test-admin-id", role="admin")
    
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[require_user] = mock_require_user
    app.dependency_overrides[require_admin] = mock_require_admin
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()

@pytest.fixture
def api(client):
    """Alias for client fixture for backward compatibility"""
    return client

# Test data fixtures
@pytest.fixture
def test_user():
    """Create test user data"""
    return {
        "id": "test-user-id",
        "email": "test@example.com",
        "role": "reader",
        "login": "testuser",
        "is_active": True
    }

@pytest.fixture
def test_admin():
    """Create test admin data"""
    return {
        "id": "test-admin-id",
        "email": "admin@example.com",
        "role": "admin",
        "login": "admin",
        "is_active": True
    }

@pytest.fixture
def test_chat():
    """Create test chat data"""
    return {
        "id": "test-chat-id",
        "name": "Test Chat",
        "tags": ["test", "example"],
        "owner_id": "test-user-id",
        "created_at": datetime.now(timezone.utc)
    }

@pytest.fixture
def test_rag_document():
    """Create test RAG document data"""
    return {
        "id": "test-doc-id",
        "name": "test.pdf",
        "title": "Test Document",
        "status": "ready",
        "user_id": "test-user-id",
        "tags": ["document", "test"],
        "created_at": datetime.now(timezone.utc)
    }

@pytest.fixture
def test_chat_message():
    """Create test chat message data"""
    return {
        "id": "test-msg-id",
        "chat_id": "test-chat-id",
        "role": "user",
        "content": {"text": "Hello, AI!"},
        "message_type": "text",
        "created_at": datetime.now(timezone.utc)
    }

# Authentication fixtures
@pytest.fixture
def admin_headers():
    """Create admin authorization headers"""
    return {
        "Authorization": "Bearer admin-test-token",
        "Content-Type": "application/json"
    }

@pytest.fixture
def user_headers():
    """Create user authorization headers"""
    return {
        "Authorization": "Bearer user-test-token",
        "Content-Type": "application/json"
    }

@pytest.fixture
def another_user_headers():
    """Create another user authorization headers"""
    return {
        "Authorization": "Bearer another-user-test-token",
        "Content-Type": "application/json"
    }

# Service mocks
@pytest.fixture
def mock_users_service():
    """Mock users service"""
    with patch('app.services.users_service_enhanced.UsersService') as mock_service:
        mock_instance = Mock()
        mock_service.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_chats_service():
    """Mock chats service"""
    with patch('app.services.chats_service_enhanced.ChatsService') as mock_service:
        mock_instance = Mock()
        mock_service.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_rag_service():
    """Mock RAG service"""
    with patch('app.services.rag_service_enhanced.RAGDocumentsService') as mock_service:
        mock_instance = Mock()
        mock_service.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_auth_service():
    """Mock auth service"""
    with patch('app.services.auth_service.AuthService') as mock_service:
        mock_instance = Mock()
        mock_service.return_value = mock_instance
        yield mock_instance

# Database mocks
@pytest.fixture
def mock_db_session():
    """Mock database session"""
    mock_session = Mock()
    mock_session.add = Mock()
    mock_session.commit = Mock()
    mock_session.rollback = Mock()
    mock_session.close = Mock()
    return mock_session

@pytest.fixture
def mock_redis():
    """Mock Redis connection"""
    with patch('app.core.redis.redis_manager') as mock_redis:
        mock_instance = Mock()
        mock_redis.get_async_redis.return_value = mock_instance
        mock_redis.get_sync_redis.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_s3():
    """Mock S3 connection"""
    with patch('app.core.s3.s3_manager') as mock_s3:
        mock_instance = Mock()
        mock_s3.health_check.return_value = True
        mock_s3.put_object.return_value = True
        mock_s3.get_object.return_value = Mock()
        yield mock_instance

# Performance test fixtures
@pytest.fixture
def performance_timer():
    """Timer for performance tests"""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
            return self.end_time - self.start_time
        
        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return Timer()

# Test markers
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "api: API tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "slow: Slow tests")

# Test data factories
class TestDataFactory:
    """Factory for creating test data"""
    
    @staticmethod
    def create_user(**kwargs):
        """Create test user"""
        defaults = {
            "id": str(uuid.uuid4()),
            "login": "testuser",
            "email": "test@example.com",
            "role": "reader",
            "is_active": True,
            "created_at": datetime.now(timezone.utc)
        }
        defaults.update(kwargs)
        return defaults
    
    @staticmethod
    def create_chat(**kwargs):
        """Create test chat"""
        defaults = {
            "id": str(uuid.uuid4()),
            "name": "Test Chat",
            "owner_id": str(uuid.uuid4()),
            "tags": ["test"],
            "created_at": datetime.now(timezone.utc)
        }
        defaults.update(kwargs)
        return defaults
    
    @staticmethod
    def create_rag_document(**kwargs):
        """Create test RAG document"""
        defaults = {
            "id": f"doc-{uuid.uuid4().hex[:8]}",
            "filename": "test.pdf",
            "title": "Test Document",
            "status": "ready",
            "user_id": str(uuid.uuid4()),
            "tags": ["document"],
            "created_at": datetime.now(timezone.utc)
        }
        defaults.update(kwargs)
        return defaults
    
    @staticmethod
    def create_chat_message(**kwargs):
        """Create test chat message"""
        defaults = {
            "id": str(uuid.uuid4()),
            "chat_id": str(uuid.uuid4()),
            "role": "user",
            "content": {"text": "Hello"},
            "message_type": "text",
            "created_at": datetime.now(timezone.utc)
        }
        defaults.update(kwargs)
        return defaults

@pytest.fixture
def test_data_factory():
    """Test data factory fixture"""
    return TestDataFactory()
