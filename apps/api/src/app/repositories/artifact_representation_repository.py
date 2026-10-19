from __future__ import annotations

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.runtime_context import ChatArtifactRepresentation
from app.models.chat_artifact_reference import ChatArtifactReference


class ArtifactRepresentationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find(self, artifact_id: UUID, fingerprint: str, extraction_key: str) -> ChatArtifactRepresentation | None:
        return await self.session.scalar(select(ChatArtifactRepresentation).where(
            ChatArtifactRepresentation.artifact_id == artifact_id,
            ChatArtifactRepresentation.source_fingerprint == fingerprint,
            ChatArtifactRepresentation.extraction_key == extraction_key))

    async def latest(self, artifact_id: UUID) -> ChatArtifactRepresentation | None:
        return await self.session.scalar(select(ChatArtifactRepresentation).where(
            ChatArtifactRepresentation.artifact_id == artifact_id).order_by(ChatArtifactRepresentation.created_at.desc()).limit(1))

    async def lock_artifact(self, artifact_id: UUID) -> None:
        await self.session.execute(select(ChatArtifactReference.id).where(
            ChatArtifactReference.id == artifact_id).with_for_update())

    async def all_for_artifact(self, artifact_id: UUID) -> list[ChatArtifactRepresentation]:
        return list((await self.session.scalars(select(ChatArtifactRepresentation).where(
            ChatArtifactRepresentation.artifact_id == artifact_id))).all())
