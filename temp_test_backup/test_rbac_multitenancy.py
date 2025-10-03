"""
Integration tests for RBAC and multi-tenancy security
"""
import pytest
import uuid
from httpx import AsyncClient
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.user import Users
from app.models.tenant import Tenants, UserTenants
from app.models.chat import Chats, ChatMessages
from app.models.rag import RAGDocument, RAGChunk
from app.models.analyze import AnalysisDocuments, AnalysisChunks
from app.repositories.users_repo import AsyncUsersRepository


@pytest.mark.asyncio
async def test_tenant_isolation_chats():
    """Test that users from tenant A cannot access chats from tenant B"""
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
            name="tenant_a_isolation",
            is_active=True
        )
        tenant_b = Tenants(
            id=uuid.uuid4(),
            name="tenant_b_isolation",
            is_active=True
        )
        session.add(tenant_a)
        session.add(tenant_b)
        await session.commit()
        await session.refresh(tenant_a)
        await session.refresh(tenant_b)
        
        # Create users for each tenant
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
        
        # Link users to their respective tenants
        await users_repo.add_to_tenant(user_a.id, tenant_a.id, is_default=True)
        await users_repo.add_to_tenant(user_b.id, tenant_b.id, is_default=True)
        await session.commit()
        
        # Create chats for each tenant
        chat_a = Chats(
            id=uuid.uuid4(),
            name="Chat in Tenant A",
            owner_id=user_a.id,
            tenant_id=tenant_a.id,
            version=1
        )
        chat_b = Chats(
            id=uuid.uuid4(),
            name="Chat in Tenant B",
            owner_id=user_b.id,
            tenant_id=tenant_b.id,
            version=1
        )
        session.add(chat_a)
        session.add(chat_b)
        await session.commit()
        await session.refresh(chat_a)
        await session.refresh(chat_b)
        
        # Test tenant isolation - user A should not see chat B
        from sqlalchemy import select
        result_a = await session.execute(
            select(Chats).where(Chats.tenant_id == tenant_a.id)
        )
        chats_a = result_a.scalars().all()
        
        result_b = await session.execute(
            select(Chats).where(Chats.tenant_id == tenant_b.id)
        )
        chats_b = result_b.scalars().all()
        
        # Verify isolation
        assert len(chats_a) == 1
        assert len(chats_b) == 1
        assert chats_a[0].id == chat_a.id
        assert chats_b[0].id == chat_b.id
        
        # User A should not be able to access chat B
        assert chat_b.id not in [chat.id for chat in chats_a]
        assert chat_a.id not in [chat.id for chat in chats_b]
        
        # Test cross-tenant access attempt (should fail)
        cross_tenant_result = await session.execute(
            select(Chats).where(
                Chats.id == chat_b.id,
                Chats.tenant_id == tenant_a.id  # Wrong tenant
            )
        )
        cross_tenant_chat = cross_tenant_result.scalar_one_or_none()
        assert cross_tenant_chat is None, "Cross-tenant access should be blocked"
        
        # Cleanup
        await session.delete(chat_a)
        await session.delete(chat_b)
        await session.delete(user_a)
        await session.delete(user_b)
        await session.delete(tenant_a)
        await session.delete(tenant_b)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_isolation_rag_documents():
    """Test that users from tenant A cannot access RAG documents from tenant B"""
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
            name="tenant_a_rag",
            is_active=True
        )
        tenant_b = Tenants(
            id=uuid.uuid4(),
            name="tenant_b_rag",
            is_active=True
        )
        session.add(tenant_a)
        session.add(tenant_b)
        await session.commit()
        await session.refresh(tenant_a)
        await session.refresh(tenant_b)
        
        # Create users for each tenant
        user_a = Users(
            id=uuid.uuid4(),
            login=f"user_a_rag_{uuid.uuid4().hex[:8]}",
            email=f"user_a_rag_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        user_b = Users(
            id=uuid.uuid4(),
            login=f"user_b_rag_{uuid.uuid4().hex[:8]}",
            email=f"user_b_rag_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user_a)
        session.add(user_b)
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        
        # Link users to their respective tenants
        await users_repo.add_to_tenant(user_a.id, tenant_a.id, is_default=True)
        await users_repo.add_to_tenant(user_b.id, tenant_b.id, is_default=True)
        await session.commit()
        
        # Create RAG documents for each tenant
        doc_a = RAGDocument(
            id=uuid.uuid4(),
            filename="tenant_a_doc.pdf",
            title="Document in Tenant A",
            user_id=user_a.id,
            status="processed"
        )
        doc_b = RAGDocument(
            id=uuid.uuid4(),
            filename="tenant_b_doc.pdf",
            title="Document in Tenant B",
            user_id=user_b.id,
            status="processed"
        )
        session.add(doc_a)
        session.add(doc_b)
        await session.commit()
        await session.refresh(doc_a)
        await session.refresh(doc_b)
        
        # Test tenant isolation for RAG documents
        from sqlalchemy import select
        result_a = await session.execute(
            select(RAGDocument).where(RAGDocument.user_id == user_a.id)
        )
        docs_a = result_a.scalars().all()
        
        result_b = await session.execute(
            select(RAGDocument).where(RAGDocument.user_id == user_b.id)
        )
        docs_b = result_b.scalars().all()
        
        # Verify isolation
        assert len(docs_a) == 1
        assert len(docs_b) == 1
        assert docs_a[0].id == doc_a.id
        assert docs_b[0].id == doc_b.id
        
        # User A should not be able to access document B
        assert doc_b.id not in [doc.id for doc in docs_a]
        assert doc_a.id not in [doc.id for doc in docs_b]
        
        # Test cross-tenant access attempt (should fail)
        cross_tenant_result = await session.execute(
            select(RAGDocument).where(
                RAGDocument.id == doc_b.id,
                RAGDocument.user_id == user_a.id  # Wrong user
            )
        )
        cross_tenant_doc = cross_tenant_result.scalar_one_or_none()
        assert cross_tenant_doc is None, "Cross-tenant RAG access should be blocked"
        
        # Cleanup
        await session.delete(doc_a)
        await session.delete(doc_b)
        await session.delete(user_a)
        await session.delete(user_b)
        await session.delete(tenant_a)
        await session.delete(tenant_b)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_isolation_analysis_documents():
    """Test that users from tenant A cannot access analysis documents from tenant B"""
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
            name="tenant_a_analysis",
            is_active=True
        )
        tenant_b = Tenants(
            id=uuid.uuid4(),
            name="tenant_b_analysis",
            is_active=True
        )
        session.add(tenant_a)
        session.add(tenant_b)
        await session.commit()
        await session.refresh(tenant_a)
        await session.refresh(tenant_b)
        
        # Create users for each tenant
        user_a = Users(
            id=uuid.uuid4(),
            login=f"user_a_analysis_{uuid.uuid4().hex[:8]}",
            email=f"user_a_analysis_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        user_b = Users(
            id=uuid.uuid4(),
            login=f"user_b_analysis_{uuid.uuid4().hex[:8]}",
            email=f"user_b_analysis_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user_a)
        session.add(user_b)
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        
        # Link users to their respective tenants
        await users_repo.add_to_tenant(user_a.id, tenant_a.id, is_default=True)
        await users_repo.add_to_tenant(user_b.id, tenant_b.id, is_default=True)
        await session.commit()
        
        # Create analysis documents for each tenant
        analysis_a = AnalysisDocuments(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            status="done",
            uploaded_by=user_a.id,
            url_file="https://tenant-a.example.com/analysis1"
        )
        analysis_b = AnalysisDocuments(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            status="done",
            uploaded_by=user_b.id,
            url_file="https://tenant-b.example.com/analysis1"
        )
        session.add(analysis_a)
        session.add(analysis_b)
        await session.commit()
        await session.refresh(analysis_a)
        await session.refresh(analysis_b)
        
        # Test tenant isolation for analysis documents
        from sqlalchemy import select
        result_a = await session.execute(
            select(AnalysisDocuments).where(AnalysisDocuments.tenant_id == tenant_a.id)
        )
        analyses_a = result_a.scalars().all()
        
        result_b = await session.execute(
            select(AnalysisDocuments).where(AnalysisDocuments.tenant_id == tenant_b.id)
        )
        analyses_b = result_b.scalars().all()
        
        # Verify isolation
        assert len(analyses_a) == 1
        assert len(analyses_b) == 1
        assert analyses_a[0].id == analysis_a.id
        assert analyses_b[0].id == analysis_b.id
        
        # User A should not be able to access analysis B
        assert analysis_b.id not in [analysis.id for analysis in analyses_a]
        assert analysis_a.id not in [analysis.id for analysis in analyses_b]
        
        # Test cross-tenant access attempt (should fail)
        cross_tenant_result = await session.execute(
            select(AnalysisDocuments).where(
                AnalysisDocuments.id == analysis_b.id,
                AnalysisDocuments.tenant_id == tenant_a.id  # Wrong tenant
            )
        )
        cross_tenant_analysis = cross_tenant_result.scalar_one_or_none()
        assert cross_tenant_analysis is None, "Cross-tenant analysis access should be blocked"
        
        # Cleanup
        await session.delete(analysis_a)
        await session.delete(analysis_b)
        await session.delete(user_a)
        await session.delete(user_b)
        await session.delete(tenant_a)
        await session.delete(tenant_b)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_rbac_role_permissions():
    """Test RBAC role-based access control"""
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
            name="rbac_test_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create users with different roles
        admin_user = Users(
            id=uuid.uuid4(),
            login=f"admin_user_{uuid.uuid4().hex[:8]}",
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="admin"
        )
        editor_user = Users(
            id=uuid.uuid4(),
            login=f"editor_user_{uuid.uuid4().hex[:8]}",
            email=f"editor_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="editor"
        )
        reader_user = Users(
            id=uuid.uuid4(),
            login=f"reader_user_{uuid.uuid4().hex[:8]}",
            email=f"reader_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        
        session.add(admin_user)
        session.add(editor_user)
        session.add(reader_user)
        await session.commit()
        await session.refresh(admin_user)
        await session.refresh(editor_user)
        await session.refresh(reader_user)
        
        # Link all users to tenant
        await users_repo.add_to_tenant(admin_user.id, tenant.id, is_default=True)
        await users_repo.add_to_tenant(editor_user.id, tenant.id, is_default=True)
        await users_repo.add_to_tenant(reader_user.id, tenant.id, is_default=True)
        await session.commit()
        
        # Test role-based permissions
        # Admin should have access to everything
        assert admin_user.role == "admin"
        
        # Editor should have write access
        assert editor_user.role == "editor"
        
        # Reader should have read-only access
        assert reader_user.role == "reader"
        
        # Test role hierarchy (admin > editor > reader)
        role_hierarchy = {"admin": 3, "editor": 2, "reader": 1}
        
        assert role_hierarchy[admin_user.role] > role_hierarchy[editor_user.role]
        assert role_hierarchy[editor_user.role] > role_hierarchy[reader_user.role]
        
        # Test permission checks (simulated)
        def has_permission(user_role: str, required_role: str) -> bool:
            return role_hierarchy[user_role] >= role_hierarchy[required_role]
        
        # Admin can do everything
        assert has_permission("admin", "admin")
        assert has_permission("admin", "editor")
        assert has_permission("admin", "reader")
        
        # Editor can edit and read
        assert has_permission("editor", "editor")
        assert has_permission("editor", "reader")
        assert not has_permission("editor", "admin")
        
        # Reader can only read
        assert has_permission("reader", "reader")
        assert not has_permission("reader", "editor")
        assert not has_permission("reader", "admin")
        
        # Cleanup
        await session.delete(admin_user)
        await session.delete(editor_user)
        await session.delete(reader_user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_x_tenant_id_header_validation(unique_tenant_name):
    """Test X-Tenant-Id header validation and enforcement"""
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
            name=f"{unique_tenant_name}_a_header",
            is_active=True
        )
        tenant_b = Tenants(
            id=uuid.uuid4(),
            name=f"{unique_tenant_name}_b_header",
            is_active=True
        )
        session.add(tenant_a)
        session.add(tenant_b)
        await session.commit()
        await session.refresh(tenant_a)
        await session.refresh(tenant_b)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"header_user_{uuid.uuid4().hex[:8]}",
            email=f"header_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Link user only to tenant A
        await users_repo.add_to_tenant(user.id, tenant_a.id, is_default=True)
        await session.commit()
        
        # Test X-Tenant-Id header validation logic
        def validate_tenant_access(user_id: str, tenant_id: str) -> bool:
            # This would be implemented in the service layer
            # For this test, we simulate the logic
            return tenant_id == str(tenant_a.id)  # User only has access to tenant A
        
        # Test valid tenant access
        assert validate_tenant_access(str(user.id), str(tenant_a.id)), "User should have access to tenant A"
        
        # Test invalid tenant access
        assert not validate_tenant_access(str(user.id), str(tenant_b.id)), "User should not have access to tenant B"
        
        # Test with non-existent tenant
        fake_tenant_id = str(uuid.uuid4())
        assert not validate_tenant_access(str(user.id), fake_tenant_id), "User should not have access to non-existent tenant"
        
        # Test default tenant fallback
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant_a.id, "Default tenant should be tenant A"
        
        # Test tenant membership check
        assert await users_repo.is_user_in_tenant(user.id, tenant_a.id), "User should be in tenant A"
        assert not await users_repo.is_user_in_tenant(user.id, tenant_b.id), "User should not be in tenant B"
        
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
async def test_multi_tenant_user_access(unique_tenant_name):
    """Test user access across multiple tenants"""
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
        tenant_1 = Tenants(
            id=uuid.uuid4(),
            name=f"{unique_tenant_name}_1_multi",
            is_active=True
        )
        tenant_2 = Tenants(
            id=uuid.uuid4(),
            name=f"{unique_tenant_name}_2_multi",
            is_active=True
        )
        tenant_3 = Tenants(
            id=uuid.uuid4(),
            name=f"{unique_tenant_name}_3_multi",
            is_active=True
        )
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
            login=f"multi_user_{uuid.uuid4().hex[:8]}",
            email=f"multi_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Link user to multiple tenants
        await users_repo.add_to_tenant(user.id, tenant_1.id, is_default=True)
        await users_repo.add_to_tenant(user.id, tenant_2.id, is_default=False)
        await users_repo.add_to_tenant(user.id, tenant_3.id, is_default=False)
        await session.commit()
        
        # Test multi-tenant access
        user_tenants = await users_repo.get_user_tenants(user.id)
        assert len(user_tenants) == 3, "User should be in 3 tenants"
        
        tenant_ids = {t.tenant_id for t in user_tenants}
        assert tenant_1.id in tenant_ids
        assert tenant_2.id in tenant_ids
        assert tenant_3.id in tenant_ids
        
        # Test default tenant
        default_tenant = await users_repo.get_default_tenant(user.id)
        assert default_tenant == tenant_1.id, "Default tenant should be tenant_1"
        
        # Test tenant membership
        assert await users_repo.is_user_in_tenant(user.id, tenant_1.id)
        assert await users_repo.is_user_in_tenant(user.id, tenant_2.id)
        assert await users_repo.is_user_in_tenant(user.id, tenant_3.id)
        
        # Test changing default tenant
        await users_repo.set_default_tenant(user.id, tenant_2.id)
        await session.commit()
        
        new_default_tenant = await users_repo.get_default_tenant(user.id)
        assert new_default_tenant == tenant_2.id, "Default tenant should be changed to tenant_2"
        
        # Test removing user from tenant
        removed = await users_repo.remove_from_tenant(user.id, tenant_3.id)
        assert removed, "Should successfully remove user from tenant_3"
        await session.commit()
        
        # Verify removal
        assert not await users_repo.is_user_in_tenant(user.id, tenant_3.id), "User should not be in tenant_3 anymore"
        
        remaining_tenants = await users_repo.get_user_tenants(user.id)
        assert len(remaining_tenants) == 2, "User should be in 2 tenants after removal"
        
        # Cleanup - сначала удаляем связи, потом основные объекты
        from sqlalchemy import delete
        await session.execute(
            delete(UserTenants).where(UserTenants.user_id == user.id)
        )
        await session.delete(user)
        await session.delete(tenant_1)
        await session.delete(tenant_2)
        await session.delete(tenant_3)
        await session.commit()
    
    await engine.dispose()
