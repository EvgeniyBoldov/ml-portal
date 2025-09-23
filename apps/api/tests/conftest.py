import pytest
import sys
import os

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
    "DB_URL", 
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
def db_session_commit(db_engine):
    """Create test database session with commit capability for test data setup"""
    connection = db_engine.connect()
    session = TestingSessionLocal(bind=connection)
    
    # Clear all tables before each test
    Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    
    yield session
    
    session.close()
    connection.close()

@pytest.fixture
def client(db_session, admin_user):
    """Create test client with database session override"""
    from app.api.deps import get_current_user, require_user, require_admin
    from app.api.schemas.users import UserRole
    
    # Mock authentication for tests - return different roles based on context
    def mock_get_current_user():
        from app.core.auth import UserCtx
        from fastapi import HTTPException, status
        # Import the global variable from test_rbac module
        import sys
        test_rbac_module = sys.modules.get('tests.api.test_rbac')
        current_test_role = getattr(test_rbac_module, '_current_test_role', 'reader')
        
        # Check if this is an inactive user test
        if current_test_role == "inactive":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="user_not_found_or_inactive"
            )
        
        # Use the admin user's ID for the user ID
        return UserCtx(id=str(admin_user.id), role=current_test_role)
    
    def mock_require_user():
        from app.core.auth import UserCtx
        # Import the global variable from test_rbac module
        import sys
        test_rbac_module = sys.modules.get('tests.api.test_rbac')
        current_test_role = getattr(test_rbac_module, '_current_test_role', 'reader')
        # Use the admin user's ID for the user ID
        return UserCtx(id=str(admin_user.id), role=current_test_role)
    
    def mock_require_admin():
        from app.core.auth import UserCtx
        from fastapi import HTTPException, status
        # Import the global variable from test_rbac module
        import sys
        test_rbac_module = sys.modules.get('tests.api.test_rbac')
        current_test_role = getattr(test_rbac_module, '_current_test_role', 'reader')
        
        print(f"DEBUG: mock_require_admin called, current_test_role = {current_test_role}")
        
        if current_test_role == "admin":
            return UserCtx(id=str(admin_user.id), role="admin")
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin role required."
            )
    
    def mock_require_roles_factory(*roles):
        """Mock require_roles factory to return appropriate user based on roles"""
        def check_roles():
            from app.core.auth import UserCtx
            from fastapi import HTTPException, status
            # Import the global variable from test_rbac module
            import sys
            test_rbac_module = sys.modules.get('tests.api.test_rbac')
            current_test_role = getattr(test_rbac_module, '_current_test_role', 'reader')
            
            # Check if the current role is allowed
            role_values = [r.value if hasattr(r, 'value') else r for r in roles]
            if current_test_role in role_values:
                return UserCtx(id=str(admin_user.id), role=current_test_role)
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required roles: {role_values}, user role: {current_test_role}"
                )
        return check_roles
    
    # Create specific mocks for different role requirements
    def mock_require_admin_role():
        from app.core.auth import UserCtx
        return UserCtx(id=str(admin_user.id), role="admin")
    
    def mock_require_reader_role():
        from app.core.auth import UserCtx
        return UserCtx(id=str(admin_user.id), role="reader")
    
    def mock_require_editor_role():
        from app.core.auth import UserCtx
        return UserCtx(id=str(admin_user.id), role="editor")
    
    # Переопределяем зависимости
    from app.api.deps import (
        db_session as db_session_dep, 
        require_roles, 
        require_editor_or_admin, 
        require_reader_or_above
    )
    app.dependency_overrides[db_session_dep] = lambda: db_session
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[require_user] = mock_require_user
    app.dependency_overrides[require_admin] = mock_require_admin
    app.dependency_overrides[require_roles] = mock_require_roles_factory
    # Mock the specific role functions
    def mock_require_editor_or_admin():
        from app.core.auth import UserCtx
        import threading
        current_test_role = getattr(threading.current_thread(), 'test_user_role', 'reader')
        if current_test_role in ["editor", "admin"]:
            # Use a dummy UUID for the user ID
            return UserCtx(id="test-user-id", role=current_test_role)
        else:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: ['editor', 'admin'], user role: {current_test_role}"
            )
    
    def mock_require_reader_or_above():
        from app.core.auth import UserCtx
        import threading
        current_test_role = getattr(threading.current_thread(), 'test_user_role', 'reader')
        if current_test_role in ["reader", "editor", "admin"]:
            # Use a dummy UUID for the user ID
            return UserCtx(id="test-user-id", role=current_test_role)
        else:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: ['reader', 'editor', 'admin'], user role: {current_test_role}"
            )
    
    app.dependency_overrides[require_editor_or_admin] = mock_require_editor_or_admin
    app.dependency_overrides[require_reader_or_above] = mock_require_reader_or_above
    
    # Дополнительно переопределяем все возможные зависимости аутентификации
    try:
        from app.api.deps import get_current_user as deps_get_current_user
        from app.api.deps import require_user as deps_require_user
        from app.api.deps import require_admin as deps_require_admin
        app.dependency_overrides[deps_get_current_user] = mock_get_current_user
        app.dependency_overrides[deps_require_user] = mock_require_user
        app.dependency_overrides[deps_require_admin] = mock_require_admin
    except ImportError:
        pass  # Если модули не найдены, пропускаем
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()

@pytest.fixture
def api(client):
    """Alias for client fixture for backward compatibility"""
    return client

@pytest.fixture
def test_user():
    """Create test user data"""
    return {
        "id": "test-user-id",
        "email": "test@example.com",
        "role": "user"
    }

@pytest.fixture
def user_headers():
    """Create user headers for authenticated requests"""
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json"
    }

@pytest.fixture
def admin_headers():
    """Create admin headers for authenticated requests"""
    return {
        "Authorization": "Bearer admin-token",
        "Content-Type": "application/json"
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


@pytest.fixture
def another_user_headers():
    """Create another user authorization headers"""
    return {
        "Authorization": "Bearer another-user-test-token",
        "Content-Type": "application/json"
    }
