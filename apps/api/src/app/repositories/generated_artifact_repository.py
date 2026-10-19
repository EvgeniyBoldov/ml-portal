from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_artifact_reference import ChatArtifactReference


class GeneratedArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_for_deliverable(self, *, chat_id: str, owner_id: str, run_id: str, key: str):
        import uuid
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                   {"key": f"file:{chat_id}:{run_id}:{key}"})
        return await self.session.scalar(select(ChatArtifactReference).where(
            ChatArtifactReference.chat_id == uuid.UUID(chat_id),
            ChatArtifactReference.owner_id == uuid.UUID(owner_id),
            ChatArtifactReference.metadata_snapshot["root_run_id"].astext == run_id,
            ChatArtifactReference.metadata_snapshot["deliverable_key"].astext == key))
