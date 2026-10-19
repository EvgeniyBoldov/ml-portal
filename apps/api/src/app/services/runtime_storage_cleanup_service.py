"""Collect storage writes abandoned by rolled-back database transactions."""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.repositories.runtime_storage_repository import RuntimeStorageRepository


class RuntimeStorageCleanupService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = RuntimeStorageRepository(session)

    async def cleanup(self, *, older_than: datetime) -> int:
        settings = get_settings()
        deleted = 0
        for bucket in {settings.S3_BUCKET_CHAT_UPLOADS, settings.S3_BUCKET_RAG, settings.S3_BUCKET_ARTIFACTS}:
            prefixes = ["chat-representations/", "runtime-context/"]
            if bucket == settings.S3_BUCKET_CHAT_UPLOADS:
                prefixes.append("chats/")
            for prefix in prefixes:
                async for item in s3_manager.iter_objects(bucket, prefix):
                    key = item["Key"]
                    if item["LastModified"] >= older_than:
                        continue
                    if prefix == "chats/" and "/generated/" not in key:
                        continue
                    if not await self.repository.referenced(bucket, key):
                        if await s3_manager.delete_object(bucket, key):
                            deleted += 1
        return deleted
