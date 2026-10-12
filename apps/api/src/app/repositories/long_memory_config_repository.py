"""Transactional selection lock and durable embedding rebuild queue."""
from uuid import UUID, uuid4

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_registry import Model


class LongMemoryConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def select_encoder(self) -> None:
        # Serialize concurrent switches, including the first selection.
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('long-memory-encoder'))"))
        await self.session.execute(update(Model).where(Model.use_for_long_memory.is_(True))
                                   .values(use_for_long_memory=False))
        await self.session.flush()

    async def request_reindex(self, model_id: UUID) -> None:
        await self.session.execute(text("""INSERT INTO long_memory_reindex_requests (id, model_id)
            VALUES (:id, :model_id)"""), {"id": uuid4(), "model_id": model_id})
