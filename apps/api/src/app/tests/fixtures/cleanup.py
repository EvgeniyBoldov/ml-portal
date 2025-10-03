"""
Фикстуры для очистки данных между тестами.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


@pytest.fixture(autouse=True, scope="function")
async def cleanup_database(db_session: AsyncSession):
    """Автоматически очищает базу данных после каждого теста."""
    yield
    
    try:
        # Очищаем данные в правильном порядке (сначала зависимые таблицы)
        cleanup_queries = [
            "DELETE FROM user_tenants",
            "DELETE FROM chat_messages", 
            "DELETE FROM chats",
            "DELETE FROM audit_logs",
            "DELETE FROM users",
            "DELETE FROM tenants",
        ]
        
        for query in cleanup_queries:
            try:
                await db_session.execute(text(query))
            except Exception:
                # Игнорируем ошибки, если таблица не существует
                pass
        
        await db_session.commit()
    except Exception:
        # Игнорируем ошибки очистки
        await db_session.rollback()
