from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_attachment_service import ChatAttachmentService


@dataclass(frozen=True)
class GeneratedArtifact:
    artifact_id: str
    file_name: str
    content_type: Optional[str]
    size_bytes: int
    metadata: dict[str, Any]


class ArtifactWriter:
    """Shared writer for all chat-owned generated artifacts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def write(
        self,
        *,
        chat_id: str,
        owner_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
    ) -> GeneratedArtifact:
        if not chat_id:
            raise ValueError("Generated artifacts require a chat context")
        if not owner_id:
            raise ValueError("Generated artifacts require an owner")
        attachment = await ChatAttachmentService(self.session).create_generated_attachment(
            chat_id=chat_id,
            owner_id=owner_id,
            filename=filename,
            content=content,
            content_type=content_type,
            metadata=metadata,
        )
        artifact_id = str(attachment.get("artifact_id") or "")
        if not artifact_id:
            raise RuntimeError("Generated attachment was not registered as an artifact")
        return GeneratedArtifact(
            artifact_id=artifact_id,
            file_name=str(attachment.get("file_name") or filename),
            content_type=attachment.get("content_type") or content_type,
            size_bytes=int(attachment.get("size_bytes") or len(content)),
            metadata=metadata or {},
        )
