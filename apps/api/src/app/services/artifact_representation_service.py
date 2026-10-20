"""Persist the shared extraction service's output without changing extraction."""
from __future__ import annotations

import hashlib
import json
import uuid
from io import BytesIO
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.models.runtime_context import ChatArtifactRepresentation
from app.models.chat_artifact_reference import ChatArtifactReference
from app.repositories.artifact_representation_repository import ArtifactRepresentationRepository
from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
from app.services.document_extraction_service import DocumentExtractionService, ExtractionRequest


class ArtifactRepresentationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ArtifactRepresentationRepository(session)

    async def canonical(self, *, artifact_id: str, chat_id: str, owner_id: str,
                        tenant_id: str | None, extract: bool = True) -> dict[str, Any] | None:
        """Versioned complete text for paged reads/indexing; never use a preview."""
        resolved = await ChatArtifactReferenceService(self.session).resolve(
            artifact_id=artifact_id, chat_id=chat_id, owner_id=owner_id, tenant_id=tenant_id)
        settings = get_settings()
        if resolved.size_bytes and resolved.size_bytes > settings.FILE_DATA_MAX_BYTES:
            raise ValueError("File exceeds the file-data extraction size limit")
        payload = await s3_manager.get_object(resolved.bucket, resolved.key)
        if payload is None:
            raise ValueError("Artifact content is unavailable")
        if len(payload) > settings.FILE_DATA_MAX_BYTES:
            raise ValueError("File exceeds the file-data extraction size limit")
        fingerprint = hashlib.sha256(payload).hexdigest()
        extraction_key = f"file_data:v{settings.CHAT_FILE_EXTRACTION_VERSION}:{settings.FILE_DATA_MAX_CHARS}"
        await self.repository.lock_artifact(uuid.UUID(artifact_id))
        row = await self.repository.find(uuid.UUID(artifact_id), fingerprint, extraction_key)
        if row:
            cached = await s3_manager.get_object(row.storage_bucket, row.storage_key)
            if cached is not None:
                return {**json.loads(cached), "representation_id": str(row.id), "reused": True}
        if not extract:
            return None
        extraction = await DocumentExtractionService().extract(ExtractionRequest(
            payload=payload, filename=resolved.file_name, content_type=resolved.content_type,
            profile="rag_ingest", max_bytes=settings.FILE_DATA_MAX_BYTES))
        if len(extraction.text) > settings.FILE_DATA_MAX_CHARS:
            raise ValueError("Extracted document exceeds the file-data character limit; no partial index was created")
        complete = not extraction.truncated and extraction.meta.get("docling_status") != "partial_success"
        result = {"artifact_id": artifact_id, "file_name": resolved.file_name,
                  "content_type": resolved.content_type, "size_bytes": len(payload),
                  "content": extraction.text, "source_fingerprint": fingerprint,
                  "source_complete": complete, "parser": extraction.parser, "warnings": extraction.warnings,
                  "status": ("ready" if complete else "partial") if extraction.text else "unreadable"}
        representation_id = row.id if row else uuid.uuid4()
        key = f"chat-representations/{chat_id}/{artifact_id}/{representation_id}.json"
        if not await s3_manager.upload_fileobj(resolved.bucket, key, BytesIO(json.dumps(result, ensure_ascii=False).encode())):
            raise ValueError("Could not persist extracted file content")
        if row is None:
            row = ChatArtifactRepresentation(id=representation_id, artifact_id=uuid.UUID(artifact_id),
                source_fingerprint=fingerprint, extraction_key=extraction_key,
                storage_bucket=resolved.bucket, storage_key=key)
            self.session.add(row)
        row.details = {key: value for key, value in result.items() if key != "content"}
        await self._record_manifest_representation(artifact_id=artifact_id, representation_id=representation_id,
            fingerprint=fingerprint, extraction_key=extraction_key, status=result["status"])
        await self.session.flush()
        return {**result, "representation_id": str(representation_id), "reused": False}

    async def read(self, *, artifact_id: str, chat_id: str, owner_id: str,
                   tenant_id: str | None, observer: Any = None) -> dict[str, Any]:
        # ACL is revalidated even on cache hits. A cached conversion grants no access.
        resolved = await ChatArtifactReferenceService(self.session).resolve(
            artifact_id=artifact_id, chat_id=chat_id, owner_id=owner_id, tenant_id=tenant_id)
        payload = await s3_manager.get_object(resolved.bucket, resolved.key)
        if payload is None:
            raise ValueError("Artifact content is unavailable")
        fingerprint = hashlib.sha256(payload).hexdigest()
        settings = get_settings()
        extraction_key = f"chat_preview:v{settings.CHAT_FILE_EXTRACTION_VERSION}:{settings.CHAT_FILE_READ_MAX_CHARS}"
        # Serialize conversions for the same artifact, including callers in different runs.
        await self.repository.lock_artifact(uuid.UUID(artifact_id))
        row = await self.repository.find(uuid.UUID(artifact_id), fingerprint, extraction_key)
        if row:
            cached = await s3_manager.get_object(row.storage_bucket, row.storage_key)
            if cached is not None:
                await self._record_manifest_representation(
                    artifact_id=artifact_id, representation_id=row.id,
                    fingerprint=fingerprint, extraction_key=extraction_key,
                    status=str((row.details or {}).get("status") or "unreadable"),
                )
                await self.session.flush()
                return {**json.loads(cached), "representation_id": str(row.id), "reused": True}
        extraction = await DocumentExtractionService().extract(ExtractionRequest(
            payload=payload, filename=resolved.file_name, content_type=resolved.content_type,
            profile="chat_preview", max_chars=settings.CHAT_FILE_READ_MAX_CHARS,
            max_bytes=max(settings.CHAT_FILE_READ_MAX_BYTES, len(payload)), observer=observer))
        result = {"artifact_id": artifact_id, "file_name": resolved.file_name,
                  "content_type": resolved.content_type or "application/octet-stream",
                  "size_bytes": len(payload), "representation": extraction.content_kind,
                  "content": extraction.text, "truncated": extraction.truncated,
                  "parser": extraction.parser, "warnings": extraction.warnings,
                  "source_fingerprint": fingerprint,
                  "source_complete": not extraction.truncated and (getattr(extraction, "meta", {}) or {}).get("docling_status") != "partial_success",
                  "status": "partial" if extraction.truncated or (getattr(extraction, "meta", {}) or {}).get("docling_status") == "partial_success" else ("ready" if extraction.text else "unreadable")}
        representation_id = row.id if row else uuid.uuid4()
        key = f"chat-representations/{chat_id}/{artifact_id}/{representation_id}.json"
        if not await s3_manager.upload_fileobj(resolved.bucket, key, BytesIO(json.dumps(result, ensure_ascii=False).encode())):
            raise ValueError("Could not persist extracted file content")
        if row is None:
            row = ChatArtifactRepresentation(id=representation_id, artifact_id=uuid.UUID(artifact_id),
                source_fingerprint=fingerprint, extraction_key=extraction_key,
                storage_bucket=resolved.bucket, storage_key=key)
            self.session.add(row)
        row.details = {key: value for key, value in result.items() if key != "content"}
        await self._record_manifest_representation(
            artifact_id=artifact_id, representation_id=representation_id,
            fingerprint=fingerprint, extraction_key=extraction_key,
            status=result["status"],
        )
        await self.session.flush()
        return {**result, "representation_id": str(representation_id), "reused": False}

    async def _record_manifest_representation(self, *, artifact_id: str,
                                              representation_id: uuid.UUID,
                                              fingerprint: str, extraction_key: str,
                                              status: str) -> None:
        reference = await self.session.get(ChatArtifactReference, uuid.UUID(artifact_id))
        if reference is None:
            return
        metadata = dict(reference.metadata_snapshot or {})
        metadata["representation"] = {
            "id": str(representation_id), "source_fingerprint": fingerprint,
            "extraction_profile": extraction_key, "status": status,
        }
        description = metadata.get("description")
        if (isinstance(description, dict) and description.get("source") == "model_inferred"
                and description.get("representation_id") != str(representation_id)):
            metadata.pop("description", None)
        reference.metadata_snapshot = metadata

    async def metadata(self, artifact_id: str) -> dict[str, Any]:
        """Return representation status without loading its object or extracted text."""
        row = await self.repository.latest(uuid.UUID(artifact_id))
        if row is None:
            return {"status": "unread"}
        details = dict(row.details or {})
        status = str(details.get("status") or "unreadable")
        if status not in {"ready", "partial", "unreadable"}:
            status = "unreadable"
        return {"id": str(row.id), "source_fingerprint": row.source_fingerprint,
                "extraction_profile": row.extraction_key, "status": status}

    async def delete_for_artifact(self, artifact_id: str) -> None:
        rows = await self.repository.all_for_artifact(uuid.UUID(artifact_id))
        for row in rows:
            if not await s3_manager.delete_object(row.storage_bucket, row.storage_key):
                raise ValueError("Could not delete extracted file content")
            await self.session.delete(row)
