"""
Test fixtures for database migrations and setup
"""
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
import os
import tempfile

from app.core.config import get_settings
from app.models.base import Base


@pytest.fixture(scope="function")
async def test_db_engine():
    """Create test database engine with migrations applied"""
    settings = get_settings()
    test_db_url = "postgresql+asyncpg://ml_portal_test:ml_portal_test_password@postgres-test:5432/ml_portal_test"
    
    engine = create_async_engine(
        test_db_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    
    # Apply Alembic migrations
    await apply_migrations(test_db_url)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


async def apply_migrations(database_url: str):
    """Apply Alembic migrations to test database"""
    # Create temporary alembic config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
        alembic_cfg_content = f"""
[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = {database_url}

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
        f.write(alembic_cfg_content)
        alembic_cfg_path = f.name
    
    try:
        # Change to the correct directory
        original_cwd = os.getcwd()
        os.chdir('/app/app')  # Change to app directory where migrations are located
        
        # Create alembic config
        alembic_cfg = Config(alembic_cfg_path)
        
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        
    finally:
        # Cleanup
        os.chdir(original_cwd)
        os.unlink(alembic_cfg_path)


@pytest.fixture
async def db_session(test_db_engine) -> AsyncSession:
    """Create database session with transaction rollback"""
    async_session = sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Start transaction
        async with session.begin():
            yield session
            # Rollback will happen automatically when exiting the context


@pytest.fixture
async def test_db_session(test_db_engine) -> AsyncSession:
    """Create database session with transaction rollback - alias for compatibility"""
    async_session = sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Start transaction
        async with session.begin():
            yield session
            # Rollback will happen automatically when exiting the context


@pytest.fixture
async def clean_db_session(test_db_engine) -> AsyncSession:
    """Create clean database session without existing data"""
    async_session = sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Clean all tables
        await session.execute("TRUNCATE TABLE user_tenants CASCADE")
        await session.execute("TRUNCATE TABLE users CASCADE")
        await session.execute("TRUNCATE TABLE tenants CASCADE")
        await session.execute("TRUNCATE TABLE chats CASCADE")
        await session.execute("TRUNCATE TABLE chatmessages CASCADE")
        await session.execute("TRUNCATE TABLE ragdocuments CASCADE")
        await session.execute("TRUNCATE TABLE ragchunks CASCADE")
        await session.execute("TRUNCATE TABLE analysisdocuments CASCADE")
        await session.execute("TRUNCATE TABLE analysischunks CASCADE")
        await session.commit()
        
        yield session
