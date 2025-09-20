from __future__ import annotations
from contextlib import contextmanager, asynccontextmanager
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

@contextmanager
def uow(session: Session):
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise

@asynccontextmanager
async def auow(session: AsyncSession):
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
