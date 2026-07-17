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
            return existing

        reference = ChatArtifactReference(
            id=uuid.uuid4(),
            chat_id=chat_uuid,
            owner_id=owner_uuid,
            target_kind=target.kind,
            target_id=str(target.target_id),
            collection_id=target.collection_id,
            display_name=target.display_name,
            content_type=target.content_type,
            size_bytes=target.size_bytes,
            metadata_snapshot=target.metadata or {},
        )
        self.session.add(reference)
        await self.session.flush()
        return reference

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
        return list(result.scalars().all())

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
