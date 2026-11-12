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

    async def ready(self, user_id: UUID, *, tenant_id: UUID | None = None,
                    tenant_ids: list[UUID] | None = None) -> list[ShadowInvocation]:
        query = select(ShadowInvocation).where(
                ShadowInvocation.user_id == user_id,
                ShadowInvocation.status.in_(["completed", "failed"]),
                ShadowInvocation.delivered_at.is_(None),
            )
        if tenant_ids is not None:
            query = query.where(ShadowInvocation.tenant_id.in_(tenant_ids))
        elif tenant_id is not None:
            query = query.where(ShadowInvocation.tenant_id == tenant_id)
        return list((await self.session.scalars(query.order_by(
            ShadowInvocation.created_at, ShadowInvocation.id))).all())

    async def by_idempotency_key(self, *, user_id: UUID, tenant_id: UUID,
                                 idempotency_key: str) -> ShadowInvocation | None:
        return await self.session.scalar(select(ShadowInvocation).where(
            ShadowInvocation.user_id == user_id,
            ShadowInvocation.tenant_id == tenant_id,
            ShadowInvocation.idempotency_key == idempotency_key,
        ))

    async def get_owned(self, invocation_id: UUID, user_id: UUID, *, tenant_id: UUID | None = None,
                        tenant_ids: list[UUID] | None = None, lock: bool = False) -> ShadowInvocation | None:
        query = select(ShadowInvocation).where(
            ShadowInvocation.id == invocation_id, ShadowInvocation.user_id == user_id)
        if tenant_ids is not None:
            query = query.where(ShadowInvocation.tenant_id.in_(tenant_ids))
        elif tenant_id is not None:
            query = query.where(ShadowInvocation.tenant_id == tenant_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def acknowledge(self, row: ShadowInvocation) -> None:
        if row.delivered_at is None:
            row.delivered_at = datetime.now(timezone.utc)
            await self.session.flush()
