from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.models.chat_artifact_reference import ChatArtifactReference
from app.models.chat_attachment import ChatAttachment
from app.models.collection import Collection
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership, Source
from app.services.file_delivery_service import FileDeliveryNotFoundError, FileDeliveryService, ResolvedDownload
from app.services.permission_service import PermissionService
from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.schemas.chat_artifacts import (
    ArtifactDescription,
    ArtifactOrigin,
    ChatArtifactManifest,
)


class ChatArtifactReferenceError(ValueError):
    pass


class ChatArtifactReferenceNotFound(ChatArtifactReferenceError):
    pass


class ChatArtifactAccessDenied(ChatArtifactReferenceError):
    pass


@dataclass(frozen=True)
class ArtifactTarget:
    kind: str
    target_id: str
    collection_id: Optional[uuid.UUID] = None
    display_name: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None
    source_id: Optional[str] = None
    source_type: Optional[str] = None


class ChatArtifactReferenceService:
    """Chat-scoped artifact references and access-aware target resolution."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(
        self,
        *,
        chat_id: str | uuid.UUID,
        owner_id: str | uuid.UUID,
        target: ArtifactTarget,
    ) -> ChatArtifactReference:
        chat_uuid = uuid.UUID(str(chat_id))
        owner_uuid = uuid.UUID(str(owner_id))
        existing = await self.session.scalar(
            select(ChatArtifactReference).where(
                ChatArtifactReference.chat_id == chat_uuid,
                ChatArtifactReference.target_kind == target.kind,
                ChatArtifactReference.target_id == str(target.target_id),
            )
        )
        if existing:
            existing.display_name = target.display_name or existing.display_name
            existing.content_type = target.content_type or existing.content_type
            existing.size_bytes = target.size_bytes if target.size_bytes is not None else existing.size_bytes
            existing.metadata_snapshot = self._normalized_metadata(
                artifact_id=str(existing.id), target_kind=target.kind,
                target_id=str(target.target_id), collection_id=target.collection_id,
                display_name=existing.display_name, content_type=existing.content_type,
                size_bytes=existing.size_bytes,
                metadata={**(existing.metadata_snapshot or {}), **(target.metadata or {})},
                source_id=target.source_id, source_type=target.source_type,
            )
            await self.session.flush()
            return existing

        reference_id = uuid.uuid4()
        reference = ChatArtifactReference(
            id=reference_id,
            chat_id=chat_uuid,
            owner_id=owner_uuid,
            target_kind=target.kind,
            target_id=str(target.target_id),
            collection_id=target.collection_id,
            display_name=target.display_name,
            content_type=target.content_type,
            size_bytes=target.size_bytes,
            metadata_snapshot=self._normalized_metadata(
                artifact_id=str(reference_id), target_kind=target.kind,
                target_id=str(target.target_id), collection_id=target.collection_id,
                display_name=target.display_name, content_type=target.content_type,
                size_bytes=target.size_bytes, metadata=target.metadata or {},
                source_id=target.source_id, source_type=target.source_type,
            ),
        )
        self.session.add(reference)
        await self.session.flush()
        return reference

    def _normalize_reference(self, reference: ChatArtifactReference) -> bool:
        previous = dict(reference.metadata_snapshot or {})
        origin = previous.get("origin") if isinstance(previous.get("origin"), dict) else {}
        normalized = self._normalized_metadata(
            artifact_id=str(reference.id), target_kind=reference.target_kind,
            target_id=reference.target_id, collection_id=reference.collection_id,
            display_name=reference.display_name, content_type=reference.content_type,
            size_bytes=reference.size_bytes, metadata=previous,
            source_id=origin.get("source_id"), source_type=origin.get("source_type"),
        )
        if normalized == previous:
            return False
        reference.metadata_snapshot = normalized
        return True

    @staticmethod
    def _normalized_metadata(*, artifact_id: str, target_kind: str, target_id: str,
                             collection_id: uuid.UUID | None, display_name: str | None,
                             content_type: str | None, size_bytes: int | None,
                             metadata: dict[str, Any], source_id: str | None,
                             source_type: str | None) -> dict[str, Any]:
        previous = ChatArtifactReferenceService._without_file_content(dict(metadata or {}))
        previous_origin = previous.get("origin") if isinstance(previous.get("origin"), dict) else {}
        generated = target_kind == "chat_attachment" and previous.get("status") == "generated"
        if target_kind == "collection_document":
            origin_kind = "rag_document"
        elif target_kind == "chat_attachment":
            origin_kind = "agent_generated" if generated else "user_upload"
        else:
            origin_kind = "external_file"
        origin = ArtifactOrigin(
            kind=origin_kind,
            source_id=str(source_id or previous_origin.get("source_id") or target_id),
            source_type=source_type or previous_origin.get("source_type") or target_kind,
            collection_id=str(collection_id) if collection_id else previous_origin.get("collection_id"),
            created_by_run_id=str(previous.get("root_run_id") or previous_origin.get("created_by_run_id") or "") or None,
        )
        file_metadata = {
            "name": display_name or previous.get("file_name") or "artifact",
            "media_type": content_type or previous.get("content_type"),
            "size_bytes": size_bytes if size_bytes is not None else previous.get("size_bytes"),
        }
        description = previous.get("description")
        if isinstance(description, str):
            description = {"text": description[:600], "source": "source_metadata"}
        elif isinstance(description, dict) and isinstance(description.get("text"), str):
            description = {**description, "text": description["text"][:600]}
        representation = previous.get("representation")
        result = {
            **previous,
            "schema_version": 1,
            "artifact_id": artifact_id,
            "origin": origin.model_dump(mode="json"),
            "file": file_metadata,
            "description": ArtifactDescription.model_validate(description).model_dump(mode="json") if description else None,
            "representation": representation,
            "status": str(previous.get("status") or "ready"),
        }
        return result

    @staticmethod
    def _without_file_content(value: Any, *, preserve_description_text: bool = False) -> Any:
        content_keys = {"content", "snippet", "preview", "body", "extracted_text", "file_content"}
        if isinstance(value, dict):
            return {key: ChatArtifactReferenceService._without_file_content(
                        item, preserve_description_text=preserve_description_text or key == "description")
                    for key, item in value.items()
                    if str(key).lower() not in content_keys
                    and (preserve_description_text or str(key).lower() != "text")}
        if isinstance(value, list):
            return [ChatArtifactReferenceService._without_file_content(
                item, preserve_description_text=preserve_description_text) for item in value]
        return value

    @staticmethod
    def manifest(reference: ChatArtifactReference) -> dict[str, Any]:
        """Return the normalized passport, upgrading legacy JSON metadata in memory."""
        metadata = ChatArtifactReferenceService._normalized_metadata(
            artifact_id=str(reference.id), target_kind=reference.target_kind,
            target_id=reference.target_id, collection_id=reference.collection_id,
            display_name=reference.display_name, content_type=reference.content_type,
            size_bytes=reference.size_bytes, metadata=reference.metadata_snapshot or {},
            source_id=None, source_type=None,
        )
        indexes = metadata.get("file_data") or {}
        public_indexes = {backend: {
            key: entry[key] for key in ("status", "representation_id", "source_fingerprint", "chunk_count", "expires_at")
            if key in entry} for backend, entry in indexes.items() if isinstance(entry, dict)}
        for entry in public_indexes.values():
            if entry.get("expires_at", 0) <= datetime.now(timezone.utc).timestamp():
                entry["status"] = "expired"
            elif ((metadata.get("representation") or {}).get("source_fingerprint")
                  and entry.get("source_fingerprint") != metadata["representation"]["source_fingerprint"]):
                entry["status"] = "stale"
        return ChatArtifactManifest.model_validate({
            "schema_version": metadata["schema_version"],
            "artifact_id": str(reference.id), "origin": metadata["origin"],
            "file": metadata["file"], "description": metadata.get("description"),
            "representation": metadata.get("representation"), "status": metadata["status"],
            "attributes": {**{key: value for key, value in metadata.items()
                           if key not in {"schema_version", "artifact_id", "origin", "file", "description", "representation", "status", "file_data"}},
                           **({"file_data": public_indexes} if public_indexes else {})},
        }).model_dump(mode="json")

    async def set_description(self, *, artifact_id: str, chat_id: str, owner_id: str,
                              description: str, representation_id: str | None) -> None:
        text = description.strip()[:600]
        if not text:
            return
        reference = await self.get_reference(artifact_id=artifact_id, chat_id=chat_id, owner_id=owner_id)
        metadata = dict(reference.metadata_snapshot or {})
        metadata["description"] = ArtifactDescription(
            text=text, source="model_inferred", representation_id=representation_id,
        ).model_dump(mode="json")
        reference.metadata_snapshot = metadata
        await self.session.flush()

    async def list_for_chat(
        self,
        *,
        chat_id: str | uuid.UUID,
        owner_id: str | uuid.UUID,
    ) -> list[ChatArtifactReference]:
        result = await self.session.execute(
            select(ChatArtifactReference)
            .where(
                ChatArtifactReference.chat_id == uuid.UUID(str(chat_id)),
                ChatArtifactReference.owner_id == uuid.UUID(str(owner_id)),
            )
            .order_by(ChatArtifactReference.created_at.desc())
        )
        references = list(result.scalars().all())
        changed = False
        for reference in references:
            changed = self._normalize_reference(reference) or changed
        if changed:
            await self.session.flush()
        return references

    async def get_reference(
        self,
        *,
        artifact_id: str | uuid.UUID,
        chat_id: str | uuid.UUID,
        owner_id: str | uuid.UUID,
    ) -> ChatArtifactReference:
        try:
            artifact_uuid = uuid.UUID(str(artifact_id))
        except (TypeError, ValueError) as exc:
            raise ChatArtifactReferenceNotFound("Invalid artifact_id") from exc
        reference = await self.session.scalar(
            select(ChatArtifactReference).where(
                ChatArtifactReference.id == artifact_uuid,
                ChatArtifactReference.chat_id == uuid.UUID(str(chat_id)),
                ChatArtifactReference.owner_id == uuid.UUID(str(owner_id)),
            )
        )
        if not reference:
            raise ChatArtifactReferenceNotFound("Artifact reference not found or access denied")
        if self._normalize_reference(reference):
            await self.session.flush()
        return reference

    async def get_reference_for_target(
        self,
        *,
        target_kind: str,
        target_id: str | uuid.UUID,
        chat_id: str | uuid.UUID,
        owner_id: str | uuid.UUID,
    ) -> ChatArtifactReference:
        reference = await self.session.scalar(
            select(ChatArtifactReference).where(
                ChatArtifactReference.target_kind == target_kind,
                ChatArtifactReference.target_id == str(target_id),
                ChatArtifactReference.chat_id == uuid.UUID(str(chat_id)),
                ChatArtifactReference.owner_id == uuid.UUID(str(owner_id)),
            )
        )
        if not reference:
            raise ChatArtifactReferenceNotFound("Artifact reference not found or access denied")
        if self._normalize_reference(reference):
            await self.session.flush()
        return reference

    async def resolve(
        self,
        *,
        artifact_id: str | uuid.UUID,
        chat_id: str | uuid.UUID,
        owner_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
    ) -> ResolvedDownload:
        reference = await self.get_reference(
            artifact_id=artifact_id,
            chat_id=chat_id,
            owner_id=owner_id,
        )
        return await self._resolve_reference(reference, owner_id=owner_id, tenant_id=tenant_id)

    async def resolve_many(
        self,
        *, artifact_ids: list[str], chat_id: str | uuid.UUID,
        owner_id: str | uuid.UUID, tenant_id: str | uuid.UUID,
    ) -> dict[str, ResolvedDownload]:
        """Resolve a bounded registry batch without one lookup per reference."""
        ids: list[uuid.UUID] = []
        for raw in artifact_ids[:100]:
            try:
                ids.append(uuid.UUID(str(raw)))
            except (TypeError, ValueError):
                continue
        if not ids:
            return {}
        rows = list((await self.session.execute(
            select(ChatArtifactReference).where(
                ChatArtifactReference.id.in_(ids),
                ChatArtifactReference.chat_id == uuid.UUID(str(chat_id)),
                ChatArtifactReference.owner_id == uuid.UUID(str(owner_id)),
            )
        )).scalars().all())
        changed = False
        for reference in rows:
            changed = self._normalize_reference(reference) or changed
        if changed:
            await self.session.flush()
        resolved: dict[str, ResolvedDownload] = {}
        for reference in rows:
            try:
                resolved[str(reference.id)] = await self._resolve_reference(
                    reference, owner_id=owner_id, tenant_id=tenant_id,
                )
            except ChatArtifactReferenceError:
                continue
        return resolved

    async def _resolve_reference(
        self, reference: ChatArtifactReference, *, owner_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
    ) -> ResolvedDownload:
        kind = reference.target_kind
        if kind == "chat_attachment":
            try:
                target_uuid = uuid.UUID(reference.target_id)
            except ValueError as exc:
                raise ChatArtifactReferenceNotFound("Invalid attachment target") from exc
            row = await self.session.scalar(
                select(ChatAttachment).where(
                    ChatAttachment.id == target_uuid,
                    ChatAttachment.chat_id == reference.chat_id,
                    ChatAttachment.owner_id == reference.owner_id,
                )
            )
            if not row:
                raise ChatArtifactReferenceNotFound("Chat attachment no longer exists")
            return ResolvedDownload(
                file_id=str(reference.id),
                bucket=row.storage_bucket,
                key=row.storage_key,
                file_name=row.file_name,
                content_type=row.content_type,
                size_bytes=row.size_bytes,
            )

        if reference.collection_id:
            await self._ensure_collection_allowed(reference.collection_id, owner_id, tenant_id)

        if kind == "collection_document":
            try:
                membership_id = uuid.UUID(reference.target_id)
            except ValueError as exc:
                raise ChatArtifactReferenceNotFound("Invalid collection document target") from exc
            result = await self.session.execute(
                select(RAGDocument, Source, DocumentCollectionMembership, Collection)
                .join(Source, Source.source_id == RAGDocument.id)
                .join(DocumentCollectionMembership, DocumentCollectionMembership.source_id == Source.source_id)
                .join(Collection, Collection.id == DocumentCollectionMembership.collection_id)
                .where(DocumentCollectionMembership.id == membership_id)
            )
            row = result.one_or_none()
            if not row:
                raise ChatArtifactReferenceNotFound("Collection document no longer exists")
            document, source, membership, collection = row
            if membership.collection_id != reference.collection_id:
                raise ChatArtifactAccessDenied("Artifact collection binding mismatch")
            key = document.s3_key_raw
            if not key:
                raise ChatArtifactReferenceNotFound("Original collection document is unavailable")
            settings = get_settings()
            return ResolvedDownload(
                file_id=str(reference.id),
                bucket=settings.S3_BUCKET_RAG,
                key=key,
                file_name=document.filename,
                content_type=document.content_type,
                size_bytes=document.size_bytes,
            )

        try:
            resolved = await FileDeliveryService(
                self.session,
                _RepositoryFactoryAdapter(tenant_id),
            ).resolve(reference.target_id, owner_id=str(owner_id))
        except FileDeliveryNotFoundError as exc:
            raise ChatArtifactReferenceNotFound(str(exc)) from exc
        return ResolvedDownload(
            file_id=str(reference.id),
            bucket=resolved.bucket,
            key=resolved.key,
            file_name=resolved.file_name,
            content_type=resolved.content_type,
            size_bytes=resolved.size_bytes,
        )

    async def delete_reference(
        self,
        *,
        artifact_id: str | uuid.UUID,
        chat_id: str | uuid.UUID,
        owner_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
    ) -> dict[str, Any]:
        reference = await self.get_reference(
            artifact_id=artifact_id, chat_id=chat_id, owner_id=owner_id
        )
        from app.services.file_data_service import FileDataService
        await FileDataService(self.session).delete_indexes(reference=reference)
        from app.services.artifact_representation_service import ArtifactRepresentationService
        await ArtifactRepresentationService(self.session).delete_for_artifact(str(reference.id))
        file_name = reference.display_name or "artifact"
        if reference.target_kind == "chat_attachment":
            resolved = await self.resolve(
                artifact_id=artifact_id,
                chat_id=chat_id,
                owner_id=owner_id,
                tenant_id=tenant_id,
            )
            deleted = await s3_manager.delete_object(resolved.bucket, resolved.key)
            if not deleted:
                raise ChatArtifactReferenceError("Storage deletion failed; retry is required")
            attachment = await self.session.scalar(
                select(ChatAttachment).where(ChatAttachment.id == uuid.UUID(reference.target_id))
            )
            if attachment:
                file_name = attachment.file_name
                await self.session.delete(attachment)
        await self.session.delete(reference)
        await self.session.flush()
        return {"deleted": True, "artifact_id": str(reference.id), "file_name": file_name}

    async def cleanup_orphaned_attachments(
        self,
        *,
        older_than: datetime,
        limit: int = 500,
    ) -> int:
        result = await self.session.execute(
            select(ChatAttachment)
            .where(
                ChatAttachment.chat_id.is_not(None),
                ChatAttachment.created_at < older_than,
            )
            .order_by(ChatAttachment.created_at.asc())
            .limit(limit)
        )
        deleted = 0
        for attachment in result.scalars().all():
            ref_exists = await self.session.scalar(
                select(ChatArtifactReference.id).where(
                    ChatArtifactReference.target_kind == "chat_attachment",
                    ChatArtifactReference.target_id == str(attachment.id),
                ).limit(1)
            )
            if ref_exists:
                continue
            try:
                await s3_manager.delete_object(attachment.storage_bucket, attachment.storage_key)
                await self.session.delete(attachment)
                deleted += 1
            except Exception:
                continue
        await self.session.flush()
        return deleted

    async def _ensure_collection_allowed(
        self,
        collection_id: uuid.UUID,
        owner_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID,
    ) -> None:
        collection = await self.session.scalar(select(Collection).where(Collection.id == collection_id))
        if not collection or not collection.is_active:
            raise ChatArtifactAccessDenied("Collection is unavailable")
        from app.services.platform_settings_service import PlatformSettingsProvider

        config = await PlatformSettingsProvider.get_instance().get_config(self.session)
        resolver = RuntimeRbacResolver(PermissionService(self.session))
        effective = await resolver.resolve_effective_permissions(
            user_id=uuid.UUID(str(owner_id)),
            tenant_id=uuid.UUID(str(tenant_id)),
            default_collection_allow=bool(config.get("default_collection_allow", True)),
        )
        if not effective.is_collection_allowed(collection.slug):
            raise ChatArtifactAccessDenied("Collection is not available to this user")


class _RepositoryFactoryAdapter:
    """Minimal adapter for FileDeliveryService's tenant lookup contract."""

    def __init__(self, tenant_id: str | uuid.UUID) -> None:
        self.tenant_id = uuid.UUID(str(tenant_id))
