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

    @pytest.fixture(scope="class")
    async def db_engine(self):
        """Создает тестовую БД engine."""
        test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
        
        engine = create_async_engine(
            test_db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        
        yield engine
        await engine.dispose()

    @pytest.fixture
    async def db_session(self, db_engine):
        """Создает тестовую сессию БД."""
        async_session = sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            yield session
            await session.rollback()

    @pytest.mark.asyncio
    async def test_database_connection(self, db_session: AsyncSession):
        """Тест подключения к базе данных."""
        # Simple query to test connection
        result = await db_session.execute(text("SELECT 1 as test_value"))
        row = result.fetchone()
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_database_schema(self, db_session: AsyncSession):
        """Тест схемы базы данных."""
        # Check if users table exists
        result = await db_session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'users'
        """))
        table_exists = result.fetchone()
        assert table_exists is not None

    @pytest.mark.asyncio
    async def test_user_crud_operations(self, db_session: AsyncSession):
        """Тест полного цикла CRUD операций с пользователями."""
        user_data = {
            "login": "crud_test",
            "email": "crud_test@example.com",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }

        try:
            # CREATE
            user = Users(**user_data)
            db_session.add(user)
            await db_session.commit()
            await db_session.refresh(user)
            
            assert user is not None
            assert user.email == user_data["email"]
            assert user.login == user_data["login"]
            assert user.is_active is True

            # READ
            result = await db_session.execute(
                select(Users).where(Users.id == user.id)
            )
            retrieved_user = result.scalar_one_or_none()
            assert retrieved_user is not None
            assert retrieved_user.email == user_data["email"]

            # UPDATE
            retrieved_user.is_active = False
            retrieved_user.login = "updated_crud_user"
            await db_session.commit()
            await db_session.refresh(retrieved_user)
            
            assert retrieved_user.login == "updated_crud_user"
            assert retrieved_user.is_active is False

            # DELETE
            await db_session.delete(retrieved_user)
            await db_session.commit()
            
            # Verify deletion
            result = await db_session.execute(
                select(Users).where(Users.id == user.id)
            )
            deleted_user = result.scalar_one_or_none()
            assert deleted_user is None

        except Exception as e:
            await db_session.rollback()
            raise e

    @pytest.mark.asyncio
    async def test_database_transaction_rollback(self, db_session: AsyncSession):
        """Тест отката транзакции при ошибке."""
        user_data = {
            "login": "transaction_test",
            "email": "transaction_test@example.com",
            "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/8K5K5K.",
            "is_active": True,
            "role": "reader"
        }

        try:
            # Start transaction
            async with db_session.begin():
                # Create user
                user = Users(**user_data)
                db_session.add(user)
                await db_session.flush()
                
                # Simulate error - this should cause rollback
                raise Exception("Simulated error")

        except Exception:
            # Assert - User should not exist due to rollback
            result = await db_session.execute(
                select(Users).where(Users.email == user_data["email"])
            )
            user = result.scalar_one_or_none()
            assert user is None

    @pytest.mark.asyncio
    async def test_user_constraints(self, db_session: AsyncSession):
        """Тест ограничений базы данных."""
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

        try:
            # Create first user
            user1 = Users(**user1_data)
            db_session.add(user1)
            await db_session.commit()
            
            # Try to create second user with same login
            user2 = Users(**user2_data)
            db_session.add(user2)
            
            # This should raise an exception due to unique constraint
            with pytest.raises(Exception):  # IntegrityError
                await db_session.commit()
                
        finally:
            # Cleanup
            try:
                await db_session.execute(
                    delete(Users).where(Users.login == "unique_test")
                )
                await db_session.commit()
            except:
                pass
