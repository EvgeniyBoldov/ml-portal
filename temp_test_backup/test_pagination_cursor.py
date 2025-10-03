"""
Integration tests for cursor-based pagination across different endpoints
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
from app.repositories.users_repo import AsyncUsersRepository


@pytest.mark.asyncio
async def test_users_pagination_cursor():
    """Test cursor-based pagination for /users endpoint"""
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
            name="pagination_test_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create 5 users
        users = []
        for i in range(5):
            user = Users(
                id=uuid.uuid4(),
                login=f"pagination_user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"pagination_{i}_{uuid.uuid4().hex[:8]}@example.com",
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
        assert len(users_page3) == 1
        assert next_cursor3 is None  # Last page
        
        # Verify no duplicates across pages
        all_user_ids = set()
        for page in [users_page1, users_page2, users_page3]:
            for user in page:
                assert user.id not in all_user_ids, "Duplicate user found across pages"
                all_user_ids.add(user.id)
        
        assert len(all_user_ids) == 5
        
        # Test limit validation
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(tenant.id, limit=0)
        
        with pytest.raises(ValueError, match="limit_out_of_range"):
            await users_repo.list_by_tenant(tenant.id, limit=101)
        
        # Cleanup
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_chats_pagination_cursor():
    """Test cursor-based pagination for /chats endpoint"""
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
            name="chats_pagination_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"chats_user_{uuid.uuid4().hex[:8]}",
            email=f"chats_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Link user to tenant
        users_repo = AsyncUsersRepository(session)
        await users_repo.add_to_tenant(user.id, tenant.id, is_default=True)
        await session.commit()
        
        # Create 5 chats
        chats = []
        for i in range(5):
            chat = Chats(
                id=uuid.uuid4(),
                name=f"Chat {i}",
                owner_id=user.id,
                tenant_id=tenant.id,
                version=1
            )
            session.add(chat)
            await session.commit()
            await session.refresh(chat)
            chats.append(chat)
        
        # Test pagination for chats (simulating the repository method)
        # This would be implemented in ChatsRepository
        from sqlalchemy import select, desc
        query = (
            select(Chats)
            .where(Chats.tenant_id == tenant.id)
            .order_by(desc(Chats.created_at), desc(Chats.id))
            .limit(3)
        )
        
        result = await session.execute(query)
        chats_page1 = result.scalars().all()
        
        assert len(chats_page1) == 3
        
        # Test cursor-based pagination (simulated)
        if len(chats_page1) > 0:
            last_chat = chats_page1[-1]
            cursor_query = (
                select(Chats)
                .where(
                    Chats.tenant_id == tenant.id,
                    # Cursor condition: (created_at, id) < (last_chat.created_at, last_chat.id)
                    (Chats.created_at < last_chat.created_at) | 
                    ((Chats.created_at == last_chat.created_at) & (Chats.id < last_chat.id))
                )
                .order_by(desc(Chats.created_at), desc(Chats.id))
                .limit(3)
            )
            
            result2 = await session.execute(cursor_query)
            chats_page2 = result2.scalars().all()
            
            assert len(chats_page2) == 2  # Remaining chats
            
            # Verify no duplicates
            page1_ids = {chat.id for chat in chats_page1}
            page2_ids = {chat.id for chat in chats_page2}
            assert len(page1_ids.intersection(page2_ids)) == 0
        
        # Cleanup
        for chat in chats:
            await session.delete(chat)
        await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_messages_pagination_cursor():
    """Test cursor-based pagination for /chats/{id}/messages endpoint"""
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
            name="messages_pagination_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create user
        user = Users(
            id=uuid.uuid4(),
            login=f"messages_user_{uuid.uuid4().hex[:8]}",
            email=f"messages_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        # Link user to tenant
        users_repo = AsyncUsersRepository(session)
        await users_repo.add_to_tenant(user.id, tenant.id, is_default=True)
        await session.commit()
        
        # Create chat
        chat = Chats(
            id=uuid.uuid4(),
            name="Messages Test Chat",
            owner_id=user.id,
            tenant_id=tenant.id,
            version=1
        )
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
        
        # Create 10 messages with small delays to ensure different timestamps
        import asyncio
        messages = []
        for i in range(10):
            message = ChatMessages(
                id=uuid.uuid4(),
                chat_id=chat.id,
                content={"text": f"Message {i}"},
                role="user",
                tenant_id=tenant.id,
                version=1
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            messages.append(message)
            # Small delay to ensure different timestamps
            await asyncio.sleep(0.01)
        
        # Test pagination for messages
        from sqlalchemy import select, desc
        query = (
            select(ChatMessages)
            .where(ChatMessages.chat_id == chat.id)
            .order_by(desc(ChatMessages.created_at), desc(ChatMessages.id))
            .limit(3)
        )
        
        result = await session.execute(query)
        messages_page1 = result.scalars().all()
        
        assert len(messages_page1) == 3
        
        # Test cursor-based pagination
        if len(messages_page1) > 0:
            last_message = messages_page1[-1]
            cursor_query = (
                select(ChatMessages)
                .where(
                    ChatMessages.chat_id == chat.id,
                    # Cursor condition
                    (ChatMessages.created_at < last_message.created_at) | 
                    ((ChatMessages.created_at == last_message.created_at) & (ChatMessages.id < last_message.id))
                )
                .order_by(desc(ChatMessages.created_at), desc(ChatMessages.id))
                .limit(3)
            )
            
            result2 = await session.execute(cursor_query)
            messages_page2 = result2.scalars().all()
            
            assert len(messages_page2) == 3
            
            # Test third page
            if len(messages_page2) > 0:
                last_message2 = messages_page2[-1]
                cursor_query3 = (
                    select(ChatMessages)
                    .where(
                        ChatMessages.chat_id == chat.id,
                        (ChatMessages.created_at < last_message2.created_at) | 
                        ((ChatMessages.created_at == last_message2.created_at) & (ChatMessages.id < last_message2.id))
                    )
                    .order_by(desc(ChatMessages.created_at), desc(ChatMessages.id))
                    .limit(3)
                )
                
                result3 = await session.execute(cursor_query3)
                messages_page3 = result3.scalars().all()
                
                assert len(messages_page3) == 3  # Remaining messages
                
                # Verify no duplicates across all pages
                all_message_ids = set()
                for page in [messages_page1, messages_page2, messages_page3]:
                    for message in page:
                        assert message.id not in all_message_ids, "Duplicate message found across pages"
                        all_message_ids.add(message.id)
                
                # Should have 9 unique messages (3+3+3)
                assert len(all_message_ids) == 9
        
        # Cleanup
        for message in messages:
            await session.delete(message)
        await session.delete(chat)
        await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_pagination_consistency_with_inserts():
    """Test pagination consistency when new items are inserted between requests"""
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
            name="consistency_test_tenant",
            is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        
        # Create initial 3 users
        users = []
        for i in range(3):
            user = Users(
                id=uuid.uuid4(),
                login=f"consistency_user_{i}_{uuid.uuid4().hex[:8]}",
                email=f"consistency_{i}_{uuid.uuid4().hex[:8]}@example.com",
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
        
        # Get first page
        users_page1, next_cursor = await users_repo.list_by_tenant(tenant.id, limit=2)
        assert len(users_page1) == 2
        assert next_cursor is not None
        
        # Insert new user between page requests
        new_user = Users(
            id=uuid.uuid4(),
            login=f"consistency_new_user_{uuid.uuid4().hex[:8]}",
            email=f"consistency_new_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            is_active=True,
            role="reader"
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        
        await users_repo.add_to_tenant(new_user.id, tenant.id, is_default=False)
        await session.commit()
        
        # Get second page with cursor
        users_page2, next_cursor2 = await users_repo.list_by_tenant(tenant.id, limit=2, cursor=next_cursor)
        
        # The new user should not appear in page2 because cursor was generated before insertion
        # This demonstrates cursor stability
        page1_ids = {user.id for user in users_page1}
        page2_ids = {user.id for user in users_page2}
        
        # No duplicates between pages
        assert len(page1_ids.intersection(page2_ids)) == 0
        
        # New user should not be in either page (cursor stability)
        assert new_user.id not in page1_ids
        assert new_user.id not in page2_ids
        
        # Cleanup
        users.append(new_user)
        for user in users:
            await session.delete(user)
        await session.delete(tenant)
        await session.commit()
    
    await engine.dispose()
