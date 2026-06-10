from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import PresignOptions, s3_manager
from app.core.cache import get_cache
from app.core.config import get_settings
from app.models.chat_attachment import ChatAttachment
from app.models.collection import Collection
from app.models.rag_ingest import Source
from app.repositories.factory import AsyncRepositoryFactory
from app.services.document_artifacts import get_document_artifact_key


CHAT_ATTACHMENT_PREFIX = "chatatt"
RAG_DOCUMENT_PREFIX = "ragdoc"
COLLECTION_EXPORT_PREFIX = "colexp"
RAG_KIND_SET = {"original", "canonical"}


@dataclass(frozen=True)
class ResolvedDownload:
    file_id: str
    bucket: str
    key: str
    file_name: str
    content_type: Optional[str]
    size_bytes: Optional[int]


class FileDeliveryNotFoundError(ValueError):
    pass


class FileDeliveryService:
    CHAT_RE = re.compile(r"^chatatt_([0-9a-fA-F-]{36})$")
    RAG_RE = re.compile(r"^ragdoc_([0-9a-fA-F-]{36})_(original|canonical)$")
    COLLECTION_EXPORT_RE = re.compile(r"^colexp_([0-9a-fA-F-]{36})$")

    def __init__(self, session: AsyncSession, repo_factory: AsyncRepositoryFactory):
        self.session = session
        self.repo_factory = repo_factory
        self.settings = get_settings()

    @staticmethod
    def make_chat_attachment_file_id(attachment_id: str) -> str:
        return f"{CHAT_ATTACHMENT_PREFIX}_{attachment_id}"

    @staticmethod
    def make_rag_document_file_id(doc_id: str, kind: str) -> str:
        return f"{RAG_DOCUMENT_PREFIX}_{doc_id}_{kind}"

    @staticmethod
    def make_collection_export_file_id(export_id: str) -> str:
        return f"{COLLECTION_EXPORT_PREFIX}_{export_id}"

    async def resolve(self, file_id: str, *, owner_id: str) -> ResolvedDownload:
        chat_match = self.CHAT_RE.match(file_id)
        if chat_match:
            return await self._resolve_chat_attachment(
                file_id=file_id,
                attachment_id=chat_match.group(1),
                owner_id=owner_id,
            )

        rag_match = self.RAG_RE.match(file_id)
        if rag_match:
            return await self._resolve_rag_document(
                file_id=file_id,
                doc_id=rag_match.group(1),
                kind=rag_match.group(2),
            )

        export_match = self.COLLECTION_EXPORT_RE.match(file_id)
        if export_match:
            return await self._resolve_collection_export(
                file_id=file_id,
                export_id=export_match.group(1),
                owner_id=owner_id,
            )

        if re.fullmatch(r"[0-9a-fA-F-]{36}", file_id):
            template_match = await self._resolve_template_upload(file_id=file_id)
            if template_match:
                return template_match

        raise FileDeliveryNotFoundError(f"Unsupported file id: {file_id}")

    async def get_presigned_url(self, resolved: ResolvedDownload, expires_in: int = 3600) -> str:
        return await s3_manager.generate_presigned_url(
            bucket=resolved.bucket,
            key=resolved.key,
            options=PresignOptions(
                method="GET",
                expires_in=expires_in,
                response_headers={
                    "ResponseContentDisposition": f'attachment; filename="{resolved.file_name}"',
                    "ResponseContentType": resolved.content_type or "application/octet-stream",
                },
            ),
        )

    async def _resolve_chat_attachment(self, *, file_id: str, attachment_id: str, owner_id: str) -> ResolvedDownload:
        try:
            att_uuid = uuid.UUID(attachment_id)
            owner_uuid = uuid.UUID(owner_id)
        except ValueError:
            raise FileDeliveryNotFoundError("Invalid attachment id")

        result = await self.session.execute(
            select(ChatAttachment).where(
                ChatAttachment.id == att_uuid,
                ChatAttachment.owner_id == owner_uuid,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise FileDeliveryNotFoundError("Attachment not found")

        return ResolvedDownload(
            file_id=file_id,
            bucket=row.storage_bucket,
            key=row.storage_key,
            file_name=row.file_name,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
        )

    async def _resolve_rag_document(self, *, file_id: str, doc_id: str, kind: str) -> ResolvedDownload:
        if kind not in RAG_KIND_SET:
            raise FileDeliveryNotFoundError("Unsupported rag download kind")
        try:
            doc_uuid = uuid.UUID(doc_id)
        except ValueError:
            raise FileDeliveryNotFoundError("Invalid document id")

        document = await self.repo_factory.get_rag_document_by_id(doc_uuid)
        if not document:
            raise FileDeliveryNotFoundError("Document not found")

        s3_key = document.s3_key_raw if kind == "original" else document.s3_key_processed
        if kind == "canonical" and not s3_key:
            source_meta_result = await self.session.execute(
                select(Source.meta).where(
                    Source.source_id == doc_uuid,
                    or_(
                        Source.tenant_id == document.tenant_id,
                        Source.tenant_id == self.repo_factory.tenant_id,
                    ),
                )
            )
            source_meta = source_meta_result.scalar_one_or_none()
            s3_key = get_document_artifact_key(source_meta, "canonical")

        if not s3_key:
            raise FileDeliveryNotFoundError("File not found")

        if kind == "canonical":
            file_name = f"{document.filename.rsplit('.', 1)[0] if '.' in document.filename else document.filename}.canonical.jsonl"
            content_type = "application/x-ndjson"
        else:
            file_name = document.filename
            content_type = document.content_type

        return ResolvedDownload(
            file_id=file_id,
            bucket=self.settings.S3_BUCKET_RAG,
            key=s3_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=document.size_bytes,
        )

    async def _resolve_collection_export(self, *, file_id: str, export_id: str, owner_id: str) -> ResolvedDownload:
        cache = await get_cache()
        meta = await cache.get(f"collection_export_meta:{export_id}")
        if not meta:
            raise FileDeliveryNotFoundError("Export not found or expired")
        if str(meta.get("status") or "") != "ready":
            raise FileDeliveryNotFoundError("Export is not ready")
        if str(meta.get("tenant_id") or "") != str(self.repo_factory.tenant_id):
            raise FileDeliveryNotFoundError("Export not found")
        if str(meta.get("owner_id") or "") != str(owner_id):
            raise FileDeliveryNotFoundError("Export access denied")

        bucket = str(meta.get("bucket") or "").strip()
        key = str(meta.get("key") or "").strip()
        if not bucket or not key:
            raise FileDeliveryNotFoundError("Export artifact missing")

        return ResolvedDownload(
            file_id=file_id,
            bucket=bucket,
            key=key,
            file_name=str(meta.get("file_name") or f"collection_export_{export_id}.csv"),
            content_type=str(meta.get("content_type") or "text/csv"),
            size_bytes=int(meta.get("size_bytes") or 0),
        )

    async def _resolve_template_upload(self, *, file_id: str) -> Optional[ResolvedDownload]:
        collections_result = await self.session.execute(
            select(Collection).where(
                Collection.tenant_id == self.repo_factory.tenant_id,
                Collection.collection_type == "template",
                Collection.is_active == True,
            )
        )
        collections = collections_result.scalars().all()
        for collection in collections:
            table_name = str(collection.table_name or "").strip()
            if not table_name:
                continue
            result = await self.session.execute(
                text(
                    f"SELECT file FROM {table_name} "
                    f"WHERE file->>'file_id' = :file_id "
                    f"LIMIT 1"
                ),
                {"file_id": file_id},
            )
            row = result.mappings().first()
            if not row:
                continue
            file_meta = row.get("file") or {}
            if not isinstance(file_meta, dict):
                continue
            bucket = str(file_meta.get("bucket") or "").strip()
            key = str(file_meta.get("s3_key") or "").strip()
            filename = str(file_meta.get("filename") or f"template_{file_id}").strip()
            content_type = str(file_meta.get("content_type") or "application/octet-stream").strip()
            if not bucket or not key:
                continue
            return ResolvedDownload(
                file_id=file_id,
                bucket=bucket,
                key=key,
                file_name=filename,
                content_type=content_type or "application/octet-stream",
                size_bytes=int(file_meta.get("size") or 0) if str(file_meta.get("size") or "").isdigit() else None,
            )
        return None
