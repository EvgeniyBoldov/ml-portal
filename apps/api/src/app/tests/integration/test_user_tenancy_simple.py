"""
Simple integration tests for user tenancy and pagination functionality
"""
import pytest
import uuid
from datetime import datetime, timedelta
from typing import List

from app.models.user import Users
from app.models.tenant import Tenants, UserTenants
from app.repositories.users_repo import UsersRepository, AsyncUsersRepository


@pytest.mark.asyncio
async def test_add_user_to_tenant_simple():
    """Test adding user to tenant with simple setup"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Create tenant
        tenant = Tenants(
            id=uuid.uuid4(),
            name="test_tenant_simple",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"test_user_simple_{uuid.uuid4().hex[:8]}",
            email=f"test_simple_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Test adding user to tenant
        users_repo = AsyncUsersRepository(session)
        user_tenant = await users_repo.add_to_tenant(user.id, tenant.id, is_default=True)
        await session.commit()
        
        # Verify link was created
        assert user_tenant.user_id == user.id
        assert user_tenant.tenant_id == tenant.id
        assert user_tenant.is_default is True
        
        # Verify user is in tenant
        assert await users_repo.is_user_in_tenant(user.id, tenant.id) is True
        
        # Test pagination
        users_list, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=10)
        assert len(users_list) == 1
        assert users_list[0].id == user.id
        assert next_cursor is None  # Only one user, no next page
        
        # Cleanup
        await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_cursor_encoding_decoding():
    """Test cursor encoding/decoding functionality"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        users_repo = AsyncUsersRepository(session)
        
        # Test cursor roundtrip
        test_data = {
            "created_at": "2024-01-01T12:00:00+00:00",
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
        
        cursor = users_repo._encode_cursor(test_data)
        decoded = users_repo._decode_cursor(cursor)
        
        assert isinstance(decoded["created_at"], datetime)
        assert isinstance(decoded["id"], uuid.UUID)
        assert decoded["created_at"].isoformat() == "2024-01-01T12:00:00+00:00"
        assert str(decoded["id"]) == "123e4567-e89b-12d3-a456-426614174000"
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_pagination_limit_validation():
    """Test pagination limit validation"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        users_repo = AsyncUsersRepository(session)
        
        # Create tenant
        tenant = Tenants(
            id=uuid.uuid4(),
            name="test_tenant_limits",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Test invalid limits
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(tenant.id, limit=0)
        
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(tenant.id, limit=101)
        
        # Test valid limit
        users_list, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=50)
        assert isinstance(users_list, list)
        assert next_cursor is None  # Empty tenant
        
        # Cleanup
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()
