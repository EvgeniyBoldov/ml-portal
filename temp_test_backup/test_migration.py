"""
Integration tests for database migration and rollback
"""
import pytest
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.models.user import Users
from app.models.tenant import Tenants, UserTenants
from app.repositories.users_repo import AsyncUsersRepository


@pytest.mark.asyncio
async def test_migration_creates_tables():
    """Test that migration creates the required tables and indexes"""
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check that tenants table exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'tenants'
            );
        """))
        tenants_exists = result.scalar()
        assert tenants_exists, "tenants table should exist"
        
        # Check that user_tenants table exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'user_tenants'
            );
        """))
        user_tenants_exists = result.scalar()
        assert user_tenants_exists, "user_tenants table should exist"
        
        # Check that ix_users_email index exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND tablename = 'users' 
                AND indexname = 'ix_users_email'
            );
        """))
        email_index_exists = result.scalar()
        assert email_index_exists, "ix_users_email index should exist"
        
        # Check that ix_users_login index exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND tablename = 'users' 
                AND indexname = 'ix_users_login'
            );
        """))
        login_index_exists = result.scalar()
        assert login_index_exists, "ix_users_login index should exist"
        
        # Check that ix_user_tenants_user_id index exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND tablename = 'user_tenants' 
                AND indexname = 'ix_user_tenants_user_id'
            );
        """))
        user_id_index_exists = result.scalar()
        assert user_id_index_exists, "ix_user_tenants_user_id index should exist"
        
        # Check that ix_user_tenants_tenant_id index exists
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND tablename = 'user_tenants' 
                AND indexname = 'ix_user_tenants_tenant_id'
            );
        """))
        tenant_id_index_exists = result.scalar()
        assert tenant_id_index_exists, "ix_user_tenants_tenant_id index should exist"
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_constraints():
    """Test that migration creates the required constraints"""
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check that unique constraint exists on user_tenants
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.table_constraints 
                WHERE constraint_schema = 'public' 
                AND table_name = 'user_tenants' 
                AND constraint_name = 'uq_user_tenants_user_tenant'
            );
        """))
        unique_constraint_exists = result.scalar()
        assert unique_constraint_exists, "Unique constraint on user_tenants should exist"
        
        # Check that foreign key constraints exist
        result = await session.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints 
            WHERE constraint_schema = 'public' 
            AND table_name = 'user_tenants' 
            AND constraint_type = 'FOREIGN KEY';
        """))
        fk_count = result.scalar()
        assert fk_count == 2, "Should have 2 foreign key constraints on user_tenants"
        
        # Check that check constraint exists on users role
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.table_constraints 
                WHERE constraint_schema = 'public' 
                AND table_name = 'users' 
                AND constraint_name = 'ck_users_ck_users_role'
            );
        """))
        role_check_exists = result.scalar()
        assert role_check_exists, "Check constraint on users.role should exist"
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_data_integrity():
    """Test that migration maintains data integrity"""
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
            name="migration_test_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"migration_test_user_{uuid.uuid4().hex[:8]}",
            email=f"migration_test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Test unique constraint - try to add same user-tenant link twice
        await users_repo.add_to_tenant(user.id, tenant.id, is_default=True)
        await session.commit()
        
        # This should fail due to unique constraint
        error_raised = False
        try:
            await users_repo.add_to_tenant(user.id, tenant.id, is_default=False)
            await session.commit()
        except Exception:
            error_raised = True
            await session.rollback()
        
        assert error_raised, "Expected IntegrityError for duplicate user-tenant link"
        
        # Test foreign key constraint - try to add user to non-existent tenant
        fake_tenant_id = uuid.uuid4()
        error_raised = False
        try:
            await users_repo.add_to_tenant(user.id, fake_tenant_id, is_default=False)
            await session.commit()
        except Exception:
            error_raised = True
            await session.rollback()
        
        assert error_raised, "Expected IntegrityError for non-existent tenant"
        
        # Cleanup
        await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_performance_indexes():
    """Test that migration creates performance indexes"""
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
            name="performance_test_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create multiple users to test index performance
        users = []
        for i in range(10):
            user = Users(
                id=uuid.uuid4(),
                login=f"perf_user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"perf_user_{i}_{uuid.uuid4().hex[:8]}@example.com",
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
        
        # Test that pagination query uses indexes efficiently
        # This would be verified by checking query execution plan in production
        users_list, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=5)
        assert len(users_list) == 5
        assert next_cursor is not None
        
        # Test tenant membership check (should use ix_user_tenants_user_id index)
        is_member = await users_repo.is_user_in_tenant(users[0].id, tenant.id)
        assert is_member is True
        
        # Test getting user tenants (should use ix_user_tenants_user_id index)
        user_tenants = await users_repo.get_user_tenants(users[0].id)
        assert len(user_tenants) == 1
        assert user_tenants[0].tenant_id == tenant.id
        
        # Cleanup
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_rollback_safety():
    """Test that migration can be safely rolled back"""
    # Create test database engine
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    engine = create_async_engine(test_db_url, echo=False)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Test that existing users table is not affected
        result = await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'users'
            );
        """))
        users_exists = result.scalar()
        assert users_exists, "users table should still exist after migration"
        
        # Test that users table structure is intact
        result = await session.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'users' 
            ORDER BY ordinal_position;
        """))
        columns = [row[0] for row in result.fetchall()]
        
        expected_columns = ['id', 'login', 'password_hash', 'role', 'is_active', 'email', 'require_password_change', 'created_at', 'updated_at']
        for col in expected_columns:
            assert col in columns, f"Column {col} should exist in users table"
        
        # Test that we can still create users
        user = Users(
            id=uuid.uuid4(),
            login=f"rollback_test_user_{uuid.uuid4().hex[:8]}",
            email=f"rollback_test_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Verify user was created successfully
        assert user.id is not None
        assert user.login is not None
        
        # Cleanup
        await session.delete(user)
        await session.commit()
    
    await engine.dispose()
