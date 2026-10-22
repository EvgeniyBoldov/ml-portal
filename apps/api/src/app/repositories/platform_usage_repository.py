"""Idempotent lifecycle projection; never retains prompts, results or credentials."""
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_usage import PlatformUsage


class PlatformUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, values: dict[str, Any], *, is_start: bool) -> None:
        stmt = insert(PlatformUsage).values(**values)
        excluded = stmt.excluded
        updates = {
            key: func.coalesce(getattr(excluded, key), getattr(PlatformUsage, key))
            for key in ("agent_slug", "model_alias", "tokens_in", "tokens_out", "token_source", "duration_ms")
        }
        updates["started_at"] = func.least(PlatformUsage.started_at, excluded.started_at)
        if not is_start:
            finished_at = case(
                (PlatformUsage.status == excluded.status, func.least(PlatformUsage.finished_at, excluded.finished_at)),
                else_=excluded.finished_at,
            )
            updates.update(status=excluded.status, finished_at=finished_at, error_code=excluded.error_code)
            updates["duration_ms"] = func.greatest(0, func.extract("epoch", finished_at - PlatformUsage.started_at) * 1000)
        await self.session.execute(stmt.on_conflict_do_update(
            index_elements=["kind", "entity_id"], set_=updates,
        ))
