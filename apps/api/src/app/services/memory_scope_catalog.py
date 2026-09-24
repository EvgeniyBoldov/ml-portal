"""Read-only catalog of migration-managed memory applicability scopes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_scope import MemoryScope


async def resolve_memory_scopes(session: AsyncSession, keys: list[str]) -> list[MemoryScope]:
    normalized = list(dict.fromkeys(str(key).strip().lower() for key in keys if str(key).strip()))
    if not normalized:
        return []
    rows = list((await session.execute(select(MemoryScope).where(
        MemoryScope.key.in_(normalized), MemoryScope.lifecycle_status == "active",
    ))).scalars().all())
    by_key = {row.key: row for row in rows}
    missing = [key for key in normalized if key not in by_key]
    if missing:
        raise ValueError(f"Unknown memory scope: {', '.join(missing)}")
    return [by_key[key] for key in normalized]


async def list_memory_scopes(session: AsyncSession, *, include_deprecated: bool = False) -> list[MemoryScope]:
    stmt = select(MemoryScope).order_by(MemoryScope.scope_type, MemoryScope.key)
    if not include_deprecated:
        stmt = stmt.where(MemoryScope.lifecycle_status == "active")
    return list((await session.execute(stmt)).scalars().all())
