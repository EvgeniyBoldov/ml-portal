"""
Простые интеграционные тесты для базы данных.
Использует реальную PostgreSQL для проверки базовых операций.
"""
import pytest
import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete, text

from app.models.user import Users


@pytest.mark.integration
class TestDatabaseIntegration:
    """Интеграционные тесты для работы с БД."""

    @pytest.mark.asyncio
    async def test_database_connection(self):
        """Тест подключения к базе данных."""
        test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
        
        engine = create_async_engine(test_db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            # Simple query to test connection
            result = await session.execute(text("SELECT 1 as test_value"))
            row = result.fetchone()
            assert row[0] == 1
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_database_schema(self):
        """Тест схемы базы данных."""
        test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
        
        engine = create_async_engine(test_db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as session:
            # Check if users table exists
            result = await session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'users'
            """))
            table_exists = result.fetchone()
            assert table_exists is not None
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_user_crud_operations(self):
        """Тест полного цикла CRUD операций с пользователями."""
        test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
        
        engine = create_async_engine(test_db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        user_data = {
            "login": "crud_test",
            "email": "crud_test@example.com",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }

        async with async_session() as session:
            try:
                # CREATE
                user = Users(**user_data)
                session.add(user)
                await session.commit()
                await session.refresh(user)
                
                assert user is not None
                assert user.email == user_data["email"]
                assert user.login == user_data["login"]
                assert user.is_active is True

                # READ
                result = await session.execute(
                    select(Users).where(Users.id == user.id)
                )
                retrieved_user = result.scalar_one_or_none()
                assert retrieved_user is not None
                assert retrieved_user.email == user_data["email"]

                # UPDATE
                retrieved_user.is_active = False
                retrieved_user.login = "updated_crud_user"
                await session.commit()
                await session.refresh(retrieved_user)
                
                assert retrieved_user.login == "updated_crud_user"
                assert retrieved_user.is_active is False

                # DELETE
                await session.delete(retrieved_user)
                await session.commit()
                
                # Verify deletion
                result = await session.execute(
                    select(Users).where(Users.id == user.id)
                )
                deleted_user = result.scalar_one_or_none()
                assert deleted_user is None

            except Exception as e:
                await session.rollback()
                raise e
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self):
        """Тест отката транзакции при ошибке."""
        test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
        
        engine = create_async_engine(test_db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        user_data = {
            "login": "transaction_test",
            "email": "transaction_test@example.com",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }

        async with async_session() as session:
            try:
                # Start transaction
                async with session.begin():
                    # Create user
                    user = Users(**user_data)
                    session.add(user)
                    await session.flush()
                    
                    # Simulate error - this should cause rollback
                    raise Exception("Simulated error")

            except Exception:
                # Assert - User should not exist due to rollback
                result = await session.execute(
                    select(Users).where(Users.email == user_data["email"])
                )
                user = result.scalar_one_or_none()
                assert user is None
        
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_user_constraints(self):
        """Тест ограничений базы данных."""
        test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
        
        engine = create_async_engine(test_db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        # Test unique constraint on login
        user1_data = {
            "login": "unique_test",
            "email": "unique_test1@example.com",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }
        
        user2_data = {
            "login": "unique_test",  # Same login
            "email": "unique_test2@example.com",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }

        async with async_session() as session:
            try:
                # Cleanup any existing data
                try:
                    await session.execute(
                        delete(Users).where(Users.login == "unique_test")
                    )
                    await session.commit()
                except:
                    await session.rollback()
                
                # Create first user
                user1 = Users(**user1_data)
                session.add(user1)
                await session.commit()
                
                # Try to create second user with same login
                user2 = Users(**user2_data)
                session.add(user2)
                
                # This should raise an exception due to unique constraint
                error_raised = False
                try:
                    await session.commit()
                except Exception:
                    error_raised = True
                    await session.rollback()
                
                assert error_raised, "Expected IntegrityError for duplicate login"
                    
            finally:
                # Cleanup
                try:
                    await session.execute(
                        delete(Users).where(Users.login == "unique_test")
                    )
                    await session.commit()
                except:
                    pass
        
        await engine.dispose()
