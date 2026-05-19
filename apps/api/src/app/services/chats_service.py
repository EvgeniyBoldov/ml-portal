from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.logging import get_logger
from app.models.chat import Chats
from app.models.chat_attachment import ChatAttachment

logger = get_logger(__name__)


class ChatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def delete_chat(self, *, chat_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        chat = (
            await self.session.execute(
                select(Chats).where(Chats.id == chat_id, Chats.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        if not chat:
            return False

        attachments = (
            await self.session.execute(
                select(ChatAttachment).where(ChatAttachment.chat_id == chat_id)
            )
        ).scalars().all()

        # Prefer folder-level cleanup to remove both uploaded and generated files.
        # Fallback to per-object cleanup if folder deletion fails.
        bucket = attachments[0].storage_bucket if attachments else None
        if bucket:
            prefix = f"chats/{chat_id}/"
            try:
                await s3_manager.delete_folder(bucket, prefix)
            except Exception as exc:  # best-effort fallback
                logger.warning(
                    "chat_folder_delete_failed_fallback_to_objects",
                    extra={
                        "chat_id": str(chat_id),
                        "bucket": bucket,
                        "prefix": prefix,
                        "error": str(exc),
                    },
                )
                for row in attachments:
                    try:
                        await s3_manager.delete_object(row.storage_bucket, row.storage_key)
                    except Exception as obj_exc:  # best-effort
                        logger.warning(
                            "chat_attachment_delete_failed",
                            extra={
                                "chat_id": str(chat_id),
                                "attachment_id": str(row.id),
                                "bucket": row.storage_bucket,
                                "key": row.storage_key,
                                "error": str(obj_exc),
                            },
                        )

        await self.session.delete(chat)
        await self.session.flush()
        return True
