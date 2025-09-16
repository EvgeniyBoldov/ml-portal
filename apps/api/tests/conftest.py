import pytest
import sys
import os

# Add the app directory to Python path
sys.path.insert(0, '/app')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.db import get_db, Base
from app.core.config import settings

# Test database URL
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
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
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def test_user():
    """Create test user data"""
    return {
        "id": "test-user-id",
        "email": "test@example.com",
        "role": "user"
    }

@pytest.fixture
def test_chat():
    """Create test chat data"""
    return {
        "id": "test-chat-id",
        "name": "Test Chat",
        "tags": ["test", "example"],
        "owner_id": "test-user-id"
    }

@pytest.fixture
def test_rag_document():
    """Create test RAG document data"""
    return {
        "id": "test-doc-id",
        "name": "test.pdf",
        "status": "ready",
        "tags": ["document", "test"]
    }
