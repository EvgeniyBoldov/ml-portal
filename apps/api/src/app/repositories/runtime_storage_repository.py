from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_attachment import ChatAttachment
from app.models.runtime_context import ChatArtifactRepresentation, RuntimeRunContext


class RuntimeStorageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def referenced(self, bucket: str, key: str) -> bool:
        if key.startswith("chat-representations/"):
            query = select(ChatArtifactRepresentation.id).where(
                ChatArtifactRepresentation.storage_bucket == bucket, ChatArtifactRepresentation.storage_key == key)
        elif key.startswith("runtime-context/"):
            query = select(RuntimeRunContext.id).where(RuntimeRunContext.manifest["bucket"].astext == bucket,
                                                       RuntimeRunContext.manifest["key"].astext == key)
        else:
            query = select(ChatAttachment.id).where(ChatAttachment.storage_bucket == bucket, ChatAttachment.storage_key == key)
        return await self.session.scalar(query.limit(1)) is not None
