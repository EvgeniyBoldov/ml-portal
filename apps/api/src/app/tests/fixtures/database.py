"""
Фикстуры для работы с базой данных в тестах.
"""
import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.db import Base
from app.models.user import User
from app.models.chat import Chat, ChatMessage


@pytest.fixture(scope="session")
async def test_db_engine():
    """Создает тестовую БД engine."""
    # Используем SQLite для тестов
    engine = create_async_engine(
        "sqlite+aiosqlite:///test.db",
        echo=False,
        future=True
    )
    
    # Создаем все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Очищаем после тестов
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine):
    """Создает тестовую сессию БД."""
    async_session = sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def sample_user(test_db_session):
    """Создает тестового пользователя."""
    user_data = {
        "email": "test_user@example.com",
        "username": "test_user",
        "password_hash": "hashed_password",
        "is_active": True,
        "is_superuser": False
    }
    
    user = User(**user_data)
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    
    yield user
    
    # Cleanup
    await test_db_session.delete(user)
    await test_db_session.commit()


@pytest.fixture
async def sample_users(test_db_session):
    """Создает несколько тестовых пользователей."""
    users_data = [
        {
            "email": f"user_{i}@example.com",
            "username": f"user_{i}",
            "password_hash": "hashed_password",
            "is_active": True,
            "is_superuser": False
        }
        for i in range(3)
    ]
    
    users = []
    for user_data in users_data:
        user = User(**user_data)
        test_db_session.add(user)
        users.append(user)
    
    await test_db_session.commit()
    
    for user in users:
        await test_db_session.refresh(user)
    
    yield users
    
    # Cleanup
    for user in users:
        await test_db_session.delete(user)
    await test_db_session.commit()


@pytest.fixture
async def sample_chat(test_db_session, sample_user):
    """Создает тестовый чат."""
    chat_data = {
        "user_id": sample_user.id,
        "title": "Test Chat",
        "created_at": "2024-01-01T00:00:00Z"
    }
    
    chat = Chat(**chat_data)
    test_db_session.add(chat)
    await test_db_session.commit()
    await test_db_session.refresh(chat)
    
    yield chat
    
    # Cleanup
    await test_db_session.delete(chat)
    await test_db_session.commit()


@pytest.fixture
async def sample_messages(test_db_session, sample_chat):
    """Создает тестовые сообщения."""
    messages_data = [
        {
            "chat_id": sample_chat.id,
            "role": "user",
            "content": "Hello, how are you?",
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "chat_id": sample_chat.id,
            "role": "assistant",
            "content": "I'm doing well, thank you!",
            "created_at": "2024-01-01T00:01:00Z"
        }
    ]
    
    messages = []
    for message_data in messages_data:
        message = ChatMessage(**message_data)
        test_db_session.add(message)
        messages.append(message)
    
    await test_db_session.commit()
    
    for message in messages:
        await test_db_session.refresh(message)
    
    yield messages
    
    # Cleanup
    for message in messages:
        await test_db_session.delete(message)
    await test_db_session.commit()


@pytest.fixture
async def clean_database(test_db_session):
    """Очищает базу данных перед тестом."""
    # Удаляем все данные из таблиц
    await test_db_session.execute("DELETE FROM chat_messages")
    await test_db_session.execute("DELETE FROM chats")
    await test_db_session.execute("DELETE FROM users")
    await test_db_session.commit()
    
    yield test_db_session
    
    # Очищаем после теста
    await test_db_session.execute("DELETE FROM chat_messages")
    await test_db_session.execute("DELETE FROM chats")
    await test_db_session.execute("DELETE FROM users")
    await test_db_session.commit()
