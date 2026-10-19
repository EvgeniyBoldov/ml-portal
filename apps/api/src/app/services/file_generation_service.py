from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.artifact_writer import ArtifactWriter, GeneratedArtifact
from app.services.file_formats import FileCodecRegistry


MAX_GENERATED_FILE_BYTES = 2 * 1024 * 1024


class FileGenerationService:
    """Use-case facade for serializing and persisting generated files."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate(
        self,
        *,
        chat_id: str,
        owner_id: str,
        filename: str,
        format_name: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> GeneratedArtifact:
        if not content:
            raise ValueError("File content must not be empty")
        encoded = FileCodecRegistry.get(format_name).encode(content, filename)
        if len(encoded.content) > MAX_GENERATED_FILE_BYTES:
            raise ValueError(
                f"File content exceeds limit of {MAX_GENERATED_FILE_BYTES} bytes"
            )
        if metadata and metadata.get("root_run_id") and metadata.get("deliverable_key") is not None:
            from app.repositories.generated_artifact_repository import GeneratedArtifactRepository
            from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
            existing = await GeneratedArtifactRepository(self.session).find_for_deliverable(
                chat_id=chat_id, owner_id=owner_id, run_id=str(metadata["root_run_id"]),
                key=str(metadata["deliverable_key"]))
            if existing:
                await ChatArtifactReferenceService(self.session).resolve(
                    artifact_id=str(existing.id), chat_id=chat_id, owner_id=owner_id, tenant_id=None)
                return GeneratedArtifact(artifact_id=str(existing.id), file_name=existing.display_name,
                    content_type=existing.content_type, size_bytes=existing.size_bytes,
                    metadata=dict(existing.metadata_snapshot or {}))
        artifact = await ArtifactWriter(self.session).write(
            chat_id=chat_id,
            owner_id=owner_id,
            filename=encoded.filename,
            content=encoded.content,
            content_type=encoded.content_type,
            metadata={
                "format": encoded.format.name,
                **(metadata or {}),
            },
        )
        return artifact
