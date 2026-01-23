from __future__ import annotations
import os
from app.core.logging import get_logger
from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

logger = get_logger(__name__)

# Global state managed by lifespan
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _db_url() -> str:
    """Get database URL from environment variables"""
    # Use ASYNC_DB_URL if available, otherwise construct from DATABASE_URL
    async_url = os.getenv("ASYNC_DB_URL")
    if async_url:
        return async_url
    
    # Fallback to DATABASE_URL with asyncpg driver
    url = os.getenv("DATABASE_URL") or "postgresql+asyncpg://ml_portal:ml_portal_password@postgres:5432/ml_portal"
    if "+asyncpg" not in url:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def _ensure_default_admin():
    """Create default admin user if it doesn't exist and link to default tenant"""
    try:
        from app.models.user import Users
        from app.models.tenant import Tenants, UserTenants
        from app.core.security import hash_password
        from sqlalchemy import select
        import uuid as uuid_module
        
        admin_login = os.getenv("DEFAULT_ADMIN_LOGIN", "admin")
        admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
        admin_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
        
        async with _session_factory() as session:
            # Get or create default tenant
            tenant_result = await session.execute(
                select(Tenants).where(Tenants.name == "default")
            )
            default_tenant = tenant_result.scalar_one_or_none()
            
            if not default_tenant:
                default_tenant = Tenants(
                    id=uuid_module.uuid4(),
                    name="default",
                    description="Default tenant",
                    is_active=True
                )
                session.add(default_tenant)
                await session.flush()
                logger.info("Created default tenant")
            
            # Get or create admin user
            result = await session.execute(
                select(Users).where(Users.login == admin_login)
            )
            admin = result.scalar_one_or_none()
            
            if not admin:
                admin = Users(
                    id=uuid_module.uuid4(),
                    login=admin_login,
                    email=admin_email,
                    password_hash=hash_password(admin_password),
                    role="admin",
                    is_active=True
                )
                session.add(admin)
                await session.flush()
                logger.info(f"Created default admin user: {admin_login}")
            
            # Ensure admin is linked to default tenant
            link_result = await session.execute(
                select(UserTenants).where(
                    UserTenants.user_id == admin.id,
                    UserTenants.tenant_id == default_tenant.id
                )
            )
            existing_link = link_result.scalar_one_or_none()
            
            if not existing_link:
                user_tenant = UserTenants(
                    id=uuid_module.uuid4(),
                    user_id=admin.id,
                    tenant_id=default_tenant.id,
                    is_default=True
                )
                session.add(user_tenant)
                logger.info(f"Linked admin user to default tenant")
            
            await session.commit()
            logger.info(f"Admin user '{admin_login}' ready with tenant '{default_tenant.name}'")
    except Exception as e:
        logger.error(f"Failed to create default admin: {e}")


async def _sync_tools_from_registry():
    """Sync tools from ToolRegistry to database"""
    try:
        from app.services.tool_sync_service import sync_tools_from_registry
        
        async with _session_factory() as session:
            stats = await sync_tools_from_registry(session)
            logger.info(f"Tool sync: {stats}")
    except Exception as e:
        logger.error(f"Failed to sync tools from registry: {e}")


async def _ensure_default_permission_set():
    """Ensure default permission set exists"""
    try:
        from app.repositories.permission_set_repository import PermissionSetRepository
        
        async with _session_factory() as session:
            repo = PermissionSetRepository(session)
            perm_set = await repo.get_or_create_default()
            await session.commit()
            logger.info(f"Default permission set ready: {perm_set.id}")
    except Exception as e:
        logger.error(f"Failed to ensure default permission set: {e}")


async def _register_embedding_models():
    """Register embedding models from database into EmbeddingServiceFactory"""
    try:
        from app.models.model_registry import Model, ModelType
        from app.adapters.embeddings import EmbeddingServiceFactory, ModelConfig
        from sqlalchemy import select
        
        async with _session_factory() as session:
            result = await session.execute(
                select(Model).where(
                    (Model.type == ModelType.EMBEDDING) &
                    (Model.enabled == True)
                )
            )
            models = result.scalars().all()
            
            for model in models:
                # Resolve API key from env var
                api_key = None
                if model.api_key_ref:
                    api_key = os.getenv(model.api_key_ref)
                
                # Get dimensions from extra_config
                dimensions = None
                if model.extra_config and 'vector_dim' in model.extra_config:
                    dimensions = model.extra_config['vector_dim']
                
                config = ModelConfig(
                    alias=model.alias,
                    provider=model.provider,
                    provider_model_name=model.provider_model_name,
                    base_url=model.base_url,
                    api_key=api_key,
                    dimensions=dimensions,
                    extra_config=model.extra_config
                )
                EmbeddingServiceFactory.register_model(config)
                logger.info(f"Registered embedding model: {model.alias} ({model.provider})")
            
            logger.info(f"Registered {len(models)} embedding models")
    except Exception as e:
        logger.error(f"Failed to register embedding models: {e}")


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan context manager for database initialization"""
    global _engine, _session_factory
    
    try:
        logger.info("Initializing database connection...")
        
        # Create async engine
        _engine = create_async_engine(
            _db_url(),
            echo=False,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=10,
            max_overflow=20,
        )
        
        # Create session factory
        _session_factory = async_sessionmaker(
            _engine, 
            expire_on_commit=False,
            class_=AsyncSession
        )
        
        logger.info("Database connection initialized successfully")
        
        # Ensure default admin exists
        await _ensure_default_admin()
        
        # Register embedding models from database
        await _register_embedding_models()
        
        # Sync tools from registry to database
        await _sync_tools_from_registry()
        
        # Ensure default permission set exists
        await _ensure_default_permission_set()
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        logger.info("Closing database connection...")
        if _engine:
            await _engine.dispose()
        logger.info("Database connection closed")


def get_engine() -> AsyncEngine:
    """Get the global async engine"""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call lifespan() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the global session factory"""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call lifespan() first.")
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency that yields an AsyncSession with explicit transaction boundaries.
    
    Usage:
        @app.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            async with db.begin():
                # Your database operations here
                pass
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def health_check() -> bool:
    """Check database connectivity with real ping"""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
