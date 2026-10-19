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
