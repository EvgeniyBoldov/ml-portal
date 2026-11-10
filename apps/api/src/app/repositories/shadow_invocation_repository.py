from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.shadow_invocation import ShadowInvocation


class ShadowInvocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, invocation: ShadowInvocation) -> None:
        self.session.add(invocation)
        await self.session.flush()

    async def ready(self, user_id: UUID) -> list[ShadowInvocation]:
        return list((await self.session.scalars(
            select(ShadowInvocation).where(
                ShadowInvocation.user_id == user_id,
                ShadowInvocation.status.in_(["completed", "failed"]),
                ShadowInvocation.delivered_at.is_(None),
            ).order_by(ShadowInvocation.created_at, ShadowInvocation.id)
        )).all())

    async def get_owned(self, invocation_id: UUID, user_id: UUID, *, lock: bool = False) -> ShadowInvocation | None:
        query = select(ShadowInvocation).where(
            ShadowInvocation.id == invocation_id, ShadowInvocation.user_id == user_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def acknowledge(self, row: ShadowInvocation) -> None:
        if row.delivered_at is None:
            row.delivered_at = datetime.now(timezone.utc)
            await self.session.flush()
