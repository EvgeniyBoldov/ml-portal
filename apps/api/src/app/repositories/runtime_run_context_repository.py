from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime_context import RuntimeRunContext


class RuntimeRunContextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, run_id: str) -> RuntimeRunContext | None:
        return await self.session.get(RuntimeRunContext, UUID(run_id))

    async def owned(self, *, run_id: str, chat_id: str, owner_id: str, branch_id: str | None) -> RuntimeRunContext | None:
        return await self.session.scalar(select(RuntimeRunContext).where(
            RuntimeRunContext.id == UUID(run_id), RuntimeRunContext.chat_id == UUID(chat_id),
            RuntimeRunContext.owner_id == UUID(owner_id), RuntimeRunContext.branch_id == branch_id))

    async def owned_many(self, *, run_ids: list[str], chat_id: str, owner_id: str,
                         branch_id: str | None) -> list[RuntimeRunContext]:
        parsed: list[UUID] = []
        for run_id in dict.fromkeys(run_ids):
            try:
                parsed.append(UUID(run_id))
            except (TypeError, ValueError):
                continue
        if not parsed:
            return []
        return list((await self.session.scalars(select(RuntimeRunContext).where(
            RuntimeRunContext.id.in_(parsed), RuntimeRunContext.chat_id == UUID(chat_id),
            RuntimeRunContext.owner_id == UUID(owner_id), RuntimeRunContext.branch_id == branch_id,
        ))).all())
