from __future__ import annotations
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .config import get_settings
from .logging import get_logger

logger = get_logger(__name__)
s = get_settings()

engine = create_engine(s.DB_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

_async_engine = None
_AsyncSessionLocal = None

def _ensure_async():
    global _async_engine, _AsyncSessionLocal
    if _async_engine is None:
        try:
            _async_engine = create_async_engine(s.ASYNC_DB_URL, future=True, pool_pre_ping=True)
            _AsyncSessionLocal = async_sessionmaker(bind=_async_engine, class_=AsyncSession, autoflush=False, autocommit=False, future=True)
        except Exception as e:
            logger.warning(f"Failed to init async engine: {e}")

@contextmanager
def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    _ensure_async()
    if _AsyncSessionLocal is None:
        raise RuntimeError("Async DB is not available")
    async with _AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

def health_check() -> bool:
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB health_check failed: {e}")
        return False
