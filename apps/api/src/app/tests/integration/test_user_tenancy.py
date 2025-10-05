"""
Integration tests for user tenancy and pagination functionality
"""
import pytest
import uuid
from datetime import datetime, timedelta
from typing import List

from app.models.user import Users
from app.models.tenant import Tenants, UserTenants
from app.repositories.users_repo import AsyncUsersRepository


class TestUserTenancyIntegration:
    """Test user tenancy M2M relationships and pagination"""

    @pytest.fixture
    async def test_tenant(self, db_session):
        """Create a test tenant"""
        tenant = Tenants(
            id=uuid.uuid4(),
            name="test_tenant_pagination",
            is_active=True
        )
        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)
        yield tenant
        try:
            await db_session.delete(tenant)
            await db_session.commit()
        except:
            pass

    @pytest.fixture
    async def test_users(self, db_session, test_tenant):
        """Create multiple test users with different creation times"""
        users_repo = AsyncUsersRepository(db_session)
        users = []
        
        # Create users with staggered creation times
        base_time = datetime.now()
        for i in range(5):
            user = Users(
                id=uuid.uuid4(),
                login=f"user_{i}",
                email=f"user_{i}@example.com",
                password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
                is_active=True,
                role="reader"
            )
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)
            
            # Link to tenant
            await users_repo.add_to_tenant(user.id, test_tenant.id, is_default=(i == 0))
            await db_session.commit()
            
            users.append(user)
            
            # Small delay to ensure different timestamps
            await db_session.execute("SELECT pg_sleep(0.01)")
        
        yield users
        
        # Cleanup
        for user in users:
            try:
                await db_session.delete(user)
                await db_session.commit()
            except:
                pass

    @pytest.mark.asyncio
    async def test_add_user_to_tenant(self, db_session, test_tenant):
        """Test adding user to tenant"""
        users_repo = AsyncUsersRepository(db_session)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login="test_user_tenant",
            email="test@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        # Add to tenant
        await users_repo.add_to_tenant(user.id, test_tenant.id, is_default=True)
        await db_session.commit()
        
        # Verify user is in tenant
        is_in_tenant = await users_repo.is_user_in_tenant(user.id, test_tenant.id)
        assert is_in_tenant
        
        # Cleanup
        try:
            await db_session.delete(user)
            await db_session.commit()
        except:
            pass

    @pytest.mark.asyncio
    async def test_set_default_tenant(self, db_session, test_tenant):
        """Test setting default tenant"""
        users_repo = AsyncUsersRepository(db_session)
        
        # Create another tenant
        tenant2 = Tenants(
            id=uuid.uuid4(),
            name="test_tenant_2",
            is_active=True
        )
        db_session.add(tenant2)
        await db_session.commit()
        await db_session.refresh(tenant2)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login="test_default_tenant",
            email="test_default@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        
        # Add to both tenants, first one as default
        await users_repo.add_to_tenant(user.id, test_tenant.id, is_default=True)
        await users_repo.add_to_tenant(user.id, tenant2.id, is_default=False)
        await db_session.commit()
        
        # Verify first tenant is default
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == test_tenant.id
        
        # Change default to second tenant
        await users_repo.set_default_tenant(user.id, tenant2.id)
        await db_session.commit()
        
        # Verify second tenant is now default
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant2.id
        
        # Cleanup
        try:
            await db_session.delete(user)
            await db_session.delete(tenant2)
            await db_session.commit()
        except:
            pass

    @pytest.mark.asyncio
    async def test_list_by_tenant_pagination(self, db_session, test_tenant, test_users):
        """Test pagination functionality"""
        users_repo = AsyncUsersRepository(db_session)
        
        # Test first page with limit=2
        users_page1, next_cursor = await users_repo.list_by_tenant(test_tenant.id, limit=2)
        
        assert len(users_page1) == 2
        assert next_cursor is not None
        
        # Test second page
        users_page2, next_cursor2 = await users_repo.list_by_tenant(test_tenant.id, limit=2, cursor=next_cursor)
        
        assert len(users_page2) == 2
        assert next_cursor2 is not None
        
        # Test third page
        users_page3, next_cursor3 = await users_repo.list_by_tenant(test_tenant.id, limit=2, cursor=next_cursor2)
        
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

    @pytest.mark.asyncio
    async def test_pagination_cursor_roundtrip(self, db_session, test_tenant, test_users):
        """Test cursor encoding/decoding"""
        users_repo = AsyncUsersRepository(db_session)
        
        # Get first page
        users_page1, next_cursor = await users_repo.list_by_tenant(test_tenant.id, limit=2)
        
        # Test cursor roundtrip
        cursor_data = users_repo._decode_cursor(next_cursor)
        assert "created_at" in cursor_data
        assert "id" in cursor_data
        assert isinstance(cursor_data["created_at"], datetime)
        assert isinstance(cursor_data["id"], uuid.UUID)
        
        # Re-encode and verify it's the same
        reencoded_cursor = users_repo._encode_cursor({
            "created_at": cursor_data["created_at"].isoformat(),
            "id": str(cursor_data["id"])
        })
        assert reencoded_cursor == next_cursor

    @pytest.mark.asyncio
    async def test_pagination_limit_validation(self, db_session, test_tenant):
        """Test limit validation"""
        users_repo = AsyncUsersRepository(db_session)
        
        # Test invalid limits
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(test_tenant.id, limit=0)
        
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(test_tenant.id, limit=101)

    @pytest.mark.asyncio
    async def test_pagination_invalid_cursor(self, db_session, test_tenant):
        """Test invalid cursor handling"""
        users_repo = AsyncUsersRepository(db_session)
        
        # Test invalid cursor
        with pytest.raises(ValueError, match="invalid_cursor"):
            await users_repo.list_by_tenant(test_tenant.id, cursor="invalid_cursor")

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, db_session):
        """Test tenant isolation - users in tenant A don't appear in tenant B"""
        users_repo = AsyncUsersRepository(db_session)
        
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
        db_session.add(tenant_a)
        db_session.add(tenant_b)
        await db_session.commit()
        await db_session.refresh(tenant_a)
        await db_session.refresh(tenant_b)
        
        # Create users
        user_a = Users(
            id=uuid.uuid4(),
            login="user_a",
            email="user_a@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        user_b = Users(
            id=uuid.uuid4(),
            login="user_b",
            email="user_b@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        db_session.add(user_a)
        db_session.add(user_b)
        await db_session.commit()
        await db_session.refresh(user_a)
        await db_session.refresh(user_b)
        
        # Link users to different tenants
        await users_repo.add_to_tenant(user_a.id, tenant_a.id, is_default=True)
        await users_repo.add_to_tenant(user_b.id, tenant_b.id, is_default=True)
        await db_session.commit()
        
        # Verify isolation
        users_in_a, _ = await users_repo.list_by_tenant(tenant_a.id)
        users_in_b, _ = await users_repo.list_by_tenant(tenant_b.id)
        
        assert len(users_in_a) == 1
        assert len(users_in_b) == 1
        assert users_in_a[0].id == user_a.id
        assert users_in_b[0].id == user_b.id
        
        # Cleanup
        try:
            await db_session.delete(user_a)
            await db_session.delete(user_b)
            await db_session.delete(tenant_a)
            await db_session.delete(tenant_b)
            await db_session.commit()
        except:
            pass

    @pytest.mark.asyncio
    async def test_empty_tenant_pagination(self, db_session):
        """Test pagination with empty tenant"""
        users_repo = AsyncUsersRepository(db_session)
        
        # Create empty tenant
        empty_tenant = Tenants(
            id=uuid.uuid4(),
            name="empty_tenant",
            is_active=True
        )
        db_session.add(empty_tenant)
        await db_session.commit()
        await db_session.refresh(empty_tenant)
        
        # Test pagination
        users, next_cursor = await users_repo.list_by_tenant(empty_tenant.id, limit=10)
        
        assert len(users) == 0
        assert next_cursor is None
        
        # Cleanup
        try:
            await db_session.delete(empty_tenant)
            await db_session.commit()
        except:
            pass
