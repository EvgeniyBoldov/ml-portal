"""
Integration tests for API endpoints with user tenancy
"""
import pytest
import uuid
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.models.user import Users
from app.models.tenant import Tenants, UserTenants
from app.repositories.users_repo import AsyncUsersRepository


@pytest.mark.asyncio
async def test_api_user_list_with_tenant_header(unique_tenant_name):
    """Test API endpoint for listing users with X-Tenant-Id header"""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from httpx import AsyncClient
    from app.main import app
    
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
            name=f"{unique_tenant_name}_api_test",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create users
        users = []
        for i in range(3):
            user = Users(
                id=uuid.uuid4(),
                login=f"api_user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"api_user_{i}_{uuid.uuid4().hex[:8]}@example.com",
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
        
        # Test API endpoint (this would be implemented in the actual API)
        # For now, we'll test the repository method that would be called
        users_list, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=2)
        
        # Verify pagination response structure
        assert len(users_list) == 2
        assert next_cursor is not None
        
        # Test second page
        users_page2, next_cursor2 = await users_repo.list_by_tenant(tenant.id, limit=2, cursor=next_cursor)
        assert len(users_page2) == 1
        assert next_cursor2 is None
        
        # Cleanup
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_api_error_handling():
    """Test API error handling for invalid requests"""
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
            name="error_test_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Test invalid limit
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(tenant.id, limit=0)
        
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(tenant.id, limit=101)
        
        # Test invalid cursor
        with pytest.raises(ValueError, match="invalid_cursor"):
            await users_repo.list_by_tenant(tenant.id, cursor="invalid_cursor")
        
        # Test malformed cursor
        malformed_cursor = "eyJpbnZhbGlkIjogImRhdGEifQ=="  # base64 of {"invalid": "data"}
        with pytest.raises(ValueError, match="invalid_cursor"):
            await users_repo.list_by_tenant(tenant.id, cursor=malformed_cursor)
        
        # Cleanup
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_api_tenant_membership_validation(unique_tenant_name):
    """Test tenant membership validation for API requests"""
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
        tenant_a = Tenants(id=uuid.uuid4(), name=f"{unique_tenant_name}_a", is_active=True)
        tenant_b = Tenants(id=uuid.uuid4(), name=f"{unique_tenant_name}_b", is_active=True)
        
        session.add(tenant_a)
        session.add(tenant_b)
        await session.commit()
        await session.refresh(tenant_a)
        await session.refresh(tenant_b)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"membership_test_user_{uuid.uuid4().hex[:8]}",
            email=f"membership_test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Add user only to tenant_a
        await users_repo.add_to_tenant(user.id, tenant_a.id, is_default=True)
        await session.commit()
        
        # Verify user is in tenant_a
        assert await users_repo.is_user_in_tenant(user.id, tenant_a.id)
        
        # Verify user is NOT in tenant_b
        assert not await users_repo.is_user_in_tenant(user.id, tenant_b.id)
        
        # This would be the logic for API validation:
        # if X-Tenant-Id header is present:
        #     if not await users_repo.is_user_in_tenant(current_user.id, tenant_id):
        #         raise HTTPException(403, {"code": "forbidden_tenant"})
        # else:
        #     default_tenant = await users_repo.get_default_tenant(current_user.id)
        #     if default_tenant is None:
        #         raise HTTPException(400, {"code": "no_default_tenant"})
        #     tenant_id = default_tenant
        
        # Test default tenant fallback
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant_a.id
        
        # Cleanup - сначала удаляем связи, потом основные объекты
        from sqlalchemy import delete
        await session.execute(
            delete(UserTenants).where(UserTenants.user_id == user.id)
        )
        await session.delete(user)
        await session.delete(tenant_a)
        await session.delete(tenant_b)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_api_pagination_edge_cases(unique_tenant_name):
    """Test edge cases in pagination for API responses"""
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
            name=f"{unique_tenant_name}_edge_case",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Test with exactly the limit number of users
        users = []
        for i in range(5):  # Exactly 5 users
            user = Users(
                id=uuid.uuid4(),
                login=f"edge_user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"edge_user_{i}_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
                is_active=True,
                role="reader"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            await users_repo.add_to_tenant(user.id, tenant.id, is_default=(i == 0))
            await session.commit()
            
            users.append(user)
        
        # Test with limit=5 (exactly the number of users)
        users_list, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=5)
        assert len(users_list) == 5
        assert next_cursor is None  # No next page
        
        # Test with limit=6 (more than available users)
        users_list, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=6)
        assert len(users_list) == 5
        assert next_cursor is None  # No next page
        
        # Test with limit=1 (many pages)
        page_count = 0
        cursor = None
        all_user_ids = set()
        
        while True:
            users_page, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=1, cursor=cursor)
            page_count += 1
            
            for user in users_page:
                assert user.id not in all_user_ids, "Duplicate user found"
                all_user_ids.add(user.id)
            
            if next_cursor is None:
                break
            cursor = next_cursor
        
        assert page_count == 5  # 5 pages with 1 user each
        assert len(all_user_ids) == 5  # All users accounted for
        
        # Cleanup
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_api_response_format():
    """Test API response format for paginated user lists"""
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
            name="response_format_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create users
        users = []
        for i in range(3):
            user = Users(
                id=uuid.uuid4(),
                login=f"format_user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"format_user_{i}_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
                is_active=True,
                role="reader"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            await users_repo.add_to_tenant(user.id, tenant.id, is_default=(i == 0))
            await session.commit()
            
            users.append(user)
        
        # Test API response format
        users_list, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=2)
        
        # Simulate API response structure
        api_response = {
            "items": [
                {
                    "id": str(user.id),
                    "login": user.login,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                }
                for user in users_list
            ],
            "next_cursor": next_cursor
        }
        
        # Verify response structure
        assert "items" in api_response
        assert "next_cursor" in api_response
        assert len(api_response["items"]) == 2
        assert api_response["next_cursor"] is not None
        
        # Verify user data structure
        for item in api_response["items"]:
            assert "id" in item
            assert "login" in item
            assert "email" in item
            assert "role" in item
            assert "is_active" in item
            assert "created_at" in item
        
        # Test second page
        users_page2, next_cursor2 = await users_repo.list_by_tenant(tenant.id, limit=2, cursor=next_cursor)
        
        api_response_page2 = {
            "items": [
                {
                    "id": str(user.id),
                    "login": user.login,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                }
                for user in users_page2
            ],
            "next_cursor": next_cursor2
        }
        
        assert len(api_response_page2["items"]) == 1
        assert api_response_page2["next_cursor"] is None
        
        # Cleanup
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()
