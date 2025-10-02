"""
Comprehensive integration tests for user tenancy and pagination functionality
"""
import pytest
import uuid
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import text

from app.models.user import Users
from app.models.tenant import Tenants, UserTenants
from app.repositories.users_repo import AsyncUsersRepository


@pytest.mark.asyncio
async def test_multiple_users_pagination():
    """Test pagination with multiple users across multiple pages"""
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
            name="test_tenant_pagination",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create 5 users with staggered creation times
        users = []
        base_time = datetime.now()
        for i in range(5):
            user = Users(
                id=uuid.uuid4(),
                login=f"user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"user_{i}_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
                is_active=True,
                role="reader"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Link to tenant
            await users_repo.add_to_tenant(user.id, tenant.id, is_default=(i == 0))
            await session.commit()
            
            users.append(user)
            
            # Small delay to ensure different timestamps
            await session.execute(text("SELECT pg_sleep(0.01)"))
        
        # Test pagination with limit=2
        users_page1, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=2)
        assert len(users_page1) == 2
        assert next_cursor is not None
        
        # Test second page
        users_page2, next_cursor2 = await users_repo.list_by_tenant(tenant.id, limit=2, cursor=next_cursor)
        assert len(users_page2) == 2
        assert next_cursor2 is not None
        
        # Test third page
        users_page3, next_cursor3 = await users_repo.list_by_tenant(tenant.id, limit=2, cursor=next_cursor2)
        assert len(users_page3) == 1  # Only 1 user left
        assert next_cursor3 is None  # No more pages
        
        # Verify no duplicates across pages
        all_user_ids = set()
        for page in [users_page1, users_page2, users_page3]:
            for user in page:
                assert user.id not in all_user_ids, "Duplicate user found across pages"
                all_user_ids.add(user.id)
        
        # Verify we got all users
        assert len(all_user_ids) == 5
        
        # Cleanup
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_isolation():
    """Test tenant isolation - users in tenant A don't appear in tenant B"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        users_repo = AsyncUsersRepository(session)
        
        # Create two tenants
        tenant_a = Tenants(
            id=uuid.uuid4(),
            name="tenant_a",
            is_active=True
        )
        tenant_b = Tenants(
            id=uuid.uuid4(),
            name="tenant_b",
            is_active=True
        )
        session.add(tenant_a)
        session.add(tenant_b)
        await session.commit()
        await session.refresh(tenant_a)
        await session.refresh(tenant_b)
        
        # Create users
        user_a = Users(
            id=uuid.uuid4(),
            login=f"user_a_{uuid.uuid4().hex[:8]}",
            email=f"user_a_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        user_b = Users(
            id=uuid.uuid4(),
            login=f"user_b_{uuid.uuid4().hex[:8]}",
            email=f"user_b_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user_a)
        session.add(user_b)
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        
        # Link users to different tenants
        await users_repo.add_to_tenant(user_a.id, tenant_a.id, is_default=True)
        await users_repo.add_to_tenant(user_b.id, tenant_b.id, is_default=True)
        await session.commit()
        
        # Verify isolation
        users_in_a, _ = await users_repo.list_by_tenant(tenant_a.id)
        users_in_b, _ = await users_repo.list_by_tenant(tenant_b.id)
        
        assert len(users_in_a) == 1
        assert len(users_in_b) == 1
        assert users_in_a[0].id == user_a.id
        assert users_in_b[0].id == user_b.id
        
        # Verify user is not in other tenant
        assert not await users_repo.is_user_in_tenant(user_a.id, tenant_b.id)
        assert not await users_repo.is_user_in_tenant(user_b.id, tenant_a.id)
        
        # Cleanup
        await session.delete(user_a)
        await session.delete(user_b)
        await session.delete(tenant_a)
        await session.delete(tenant_b)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_multiple_tenants():
    """Test user belonging to multiple tenants"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        users_repo = AsyncUsersRepository(session)
        
        # Create two tenants
        tenant_1 = Tenants(
            id=uuid.uuid4(),
            name="tenant_1",
            is_active=True
        )
        tenant_2 = Tenants(
            id=uuid.uuid4(),
            name="tenant_2",
            is_active=True
        )
        session.add(tenant_1)
        session.add(tenant_2)
        await session.commit()
        await session.refresh(tenant_1)
        await session.refresh(tenant_2)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"multi_tenant_user_{uuid.uuid4().hex[:8]}",
            email=f"multi_tenant_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Add user to both tenants
        await users_repo.add_to_tenant(user.id, tenant_1.id, is_default=True)
        await users_repo.add_to_tenant(user.id, tenant_2.id, is_default=False)
        await session.commit()
        
        # Verify user is in both tenants
        assert await users_repo.is_user_in_tenant(user.id, tenant_1.id)
        assert await users_repo.is_user_in_tenant(user.id, tenant_2.id)
        
        # Verify user appears in both tenant lists
        users_tenant_1, _ = await users_repo.list_by_tenant(tenant_1.id)
        users_tenant_2, _ = await users_repo.list_by_tenant(tenant_2.id)
        
        assert len(users_tenant_1) == 1
        assert len(users_tenant_2) == 1
        assert users_tenant_1[0].id == user.id
        assert users_tenant_2[0].id == user.id
        
        # Verify default tenant
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant_1.id
        
        # Change default tenant
        await users_repo.set_default_tenant(user.id, tenant_2.id)
        await session.commit()
        
        new_default_tenant = await users_repo.get_default_tenant(user.id)
        assert new_default_tenant == tenant_2.id
        
        # Get all tenants for user
        user_tenants = await users_repo.get_user_tenants(user.id)
        assert len(user_tenants) == 2
        tenant_ids = {t.id for t in user_tenants}
        assert tenant_1.id in tenant_ids
        assert tenant_2.id in tenant_ids
        
        # Cleanup
        await session.delete(user)
        await session.delete(tenant_1)
        await session.delete(tenant_2)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_default_tenant_management():
    """Test default tenant assignment and management"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        users_repo = AsyncUsersRepository(session)
        
        # Create three tenants
        tenant_1 = Tenants(id=uuid.uuid4(), name="tenant_1", is_active=True)
        tenant_2 = Tenants(id=uuid.uuid4(), name="tenant_2", is_active=True)
        tenant_3 = Tenants(id=uuid.uuid4(), name="tenant_3", is_active=True)
        
        session.add(tenant_1)
        session.add(tenant_2)
        session.add(tenant_3)
        await session.commit()
        await session.refresh(tenant_1)
        await session.refresh(tenant_2)
        await session.refresh(tenant_3)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"default_test_user_{uuid.uuid4().hex[:8]}",
            email=f"default_test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Add user to all tenants, first one as default
        await users_repo.add_to_tenant(user.id, tenant_1.id, is_default=True)
        await users_repo.add_to_tenant(user.id, tenant_2.id, is_default=False)
        await users_repo.add_to_tenant(user.id, tenant_3.id, is_default=False)
        await session.commit()
        
        # Verify initial default
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant_1.id
        
        # Change default to tenant_2
        await users_repo.set_default_tenant(user.id, tenant_2.id)
        await session.commit()
        
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant_2.id
        
        # Verify only one default exists
        # We need to check the UserTenants directly, not the Tenants
        from sqlalchemy import select
        result = await session.execute(
            select(UserTenants).where(UserTenants.user_id == user.id)
        )
        user_tenant_links = result.scalars().all()
        default_count = sum(1 for ut in user_tenant_links if ut.is_default)
        assert default_count == 1
        
        # Change default to tenant_3
        await users_repo.set_default_tenant(user.id, tenant_3.id)
        await session.commit()
        
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant_3.id
        
        # Cleanup
        await session.delete(user)
        await session.delete(tenant_1)
        await session.delete(tenant_2)
        await session.delete(tenant_3)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_cursor_stability_with_equal_timestamps():
    """Test cursor stability when users have equal created_at timestamps"""
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
            name="test_tenant_stability",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create users with same timestamp (simulate concurrent creation)
        fixed_time = datetime.now()
        users = []
        
        for i in range(3):
            user = Users(
                id=uuid.uuid4(),
                login=f"stability_user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"stability_{i}_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
                is_active=True,
                role="reader"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Link to tenant
            await users_repo.add_to_tenant(user.id, tenant.id, is_default=(i == 0))
            await session.commit()
            
            users.append(user)
        
        # Test pagination - should be stable due to ID tie-breaker
        users_page1, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=2)
        assert len(users_page1) == 2
        assert next_cursor is not None
        
        # Test cursor roundtrip
        cursor_data = users_repo._decode_cursor(next_cursor)
        assert "created_at" in cursor_data
        assert "id" in cursor_data
        assert isinstance(cursor_data["created_at"], datetime)
        assert isinstance(cursor_data["id"], uuid.UUID)
        
        # Test second page
        users_page2, next_cursor2 = await users_repo.list_by_tenant(tenant.id, limit=2, cursor=next_cursor)
        assert len(users_page2) == 1
        assert next_cursor2 is None
        
        # Verify no duplicates
        all_user_ids = set()
        for page in [users_page1, users_page2]:
            for user in page:
                assert user.id not in all_user_ids, "Duplicate user found across pages"
                all_user_ids.add(user.id)
        
        assert len(all_user_ids) == 3
        
        # Cleanup
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_remove_user_from_tenant():
    """Test removing user from tenant"""
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
            name="test_tenant_removal",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"removal_test_user_{uuid.uuid4().hex[:8]}",
            email=f"removal_test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Add user to tenant
        await users_repo.add_to_tenant(user.id, tenant.id, is_default=True)
        await session.commit()
        
        # Verify user is in tenant
        assert await users_repo.is_user_in_tenant(user.id, tenant.id)
        users_list, _ = await users_repo.list_by_tenant(tenant.id)
        assert len(users_list) == 1
        assert users_list[0].id == user.id
        
        # Remove user from tenant
        removed = await users_repo.remove_from_tenant(user.id, tenant.id)
        assert removed is True
        await session.commit()
        
        # Verify user is no longer in tenant
        assert not await users_repo.is_user_in_tenant(user.id, tenant.id)
        users_list, _ = await users_repo.list_by_tenant(tenant.id)
        assert len(users_list) == 0
        
        # Try to remove again (should return False)
        removed_again = await users_repo.remove_from_tenant(user.id, tenant.id)
        assert removed_again is False
        
        # Cleanup
        await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_empty_tenant_operations():
    """Test operations on empty tenant"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        users_repo = AsyncUsersRepository(session)
        
        # Create empty tenant
        empty_tenant = Tenants(
            id=uuid.uuid4(),
            name="empty_tenant",
            is_active=True
        )
        session.add(empty_tenant)
        await session.commit()
        await session.refresh(empty_tenant)
        
        # Test pagination on empty tenant
        users, next_cursor = await users_repo.list_by_tenant(empty_tenant.id, limit=10)
        assert len(users) == 0
        assert next_cursor is None
        
        # Test with cursor (should still return empty)
        fake_cursor = users_repo._encode_cursor({
            "created_at": "2024-01-01T12:00:00+00:00",
            "id": str(uuid.uuid4())
        })
        users, next_cursor = await users_repo.list_by_tenant(empty_tenant.id, limit=10, cursor=fake_cursor)
        assert len(users) == 0
        assert next_cursor is None
        
        # Cleanup
        await session.delete(empty_tenant)
        await session.commit()
    
    await engine.dispose()
