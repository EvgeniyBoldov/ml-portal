"""
CollectionDocumentUploadService — persistence layer for document-collection uploads.

Responsibilities:
- validate that the target collection is a document collection
- upload the source file to S3
- insert a row into the collection table
- create RAGDocument + Source records
- initialize RAG statuses
- update collection counters

Pipeline dispatch is handled by the caller via RAGIngestService.
"""
from __future__ import annotations

import uuid
from typing import Optional, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType, FieldType
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source, DocumentCollectionMembership
from app.repositories.factory import AsyncRepositoryFactory
from app.services.collection_service import CollectionService
from app.core.exceptions import CollectionNotFoundError, CollectionDocumentUploadError, NotDocumentCollectionError
from app.services.document_artifacts import build_document_source_meta
from app.services.rag_event_publisher import RAGEventPublisher
from app.services.rag_status_manager import RAGStatusManager
from app.services.upload_intake_policy import UploadIntakePolicy
from app.storage.paths import calculate_file_checksum, get_origin_path

logger = get_logger(__name__)



class CollectionDocumentUploadService:
    """
    Persistence service for document-collection uploads.

    The caller decides whether to start RAG ingest after upload.
    """

    def __init__(
        self,
        session: AsyncSession,
        repo_factory: AsyncRepositoryFactory,
        event_publisher: Optional[RAGEventPublisher] = None,
    ):
        self.session = session
        self.repo_factory = repo_factory
        self.event_publisher = event_publisher
        self._tenant_id = repo_factory.tenant_id

    async def upload_document(
        self,
        collection_id: uuid.UUID,
        file_content: bytes,
        filename: str,
        user_id: uuid.UUID,
        content_type: Optional[str] = None,
        title: Optional[str] = None,
        source: Optional[str] = None,
        scope: Optional[str] = None,
        tags: Optional[List[str]] = None,
        meta_fields: Optional[dict] = None,
    ) -> dict:
        """Upload a file into a document collection and persist RAG bookkeeping."""
        collection = await self._get_document_collection(collection_id)
        UploadIntakePolicy.validate_document_upload(
            filename=filename,
            content_type=content_type,
            size_bytes=len(file_content),
        )

        doc_id = uuid.uuid4()
        settings = get_settings()
        file_checksum = calculate_file_checksum(file_content)
        s3_key = get_origin_path(self._tenant_id, doc_id, filename, file_checksum)
        bucket = settings.S3_BUCKET_RAG
        uploaded = await self._upload_to_s3(file_content, s3_key, bucket)
        if not uploaded:
            raise CollectionDocumentUploadError(f"Failed to upload file to s3://{bucket}/{s3_key}")

        try:
            file_meta = {
                "s3_key": s3_key,
                "filename": filename,
                "content_type": content_type,
                "size": len(file_content),
                "doc_id": str(doc_id),
            }

            row_id = await self._insert_collection_row(
                collection=collection,
                file_meta=file_meta,
                title=title or filename,
                source_val=source,
                scope=scope,
                tags=",".join(tags) if tags else None,
                meta_fields=meta_fields or {},
            )

            rag_doc = RAGDocument(
                id=doc_id,
                tenant_id=self._tenant_id,
                user_id=user_id,
                filename=filename,
                title=title or filename,
                content_type=content_type,
                size=len(file_content),
                size_bytes=len(file_content),
                tags=tags or [],
                s3_key_raw=s3_key,
                status="uploaded",
                scope=scope or "collection",
            )
            self.session.add(rag_doc)
            await self.session.flush()

            source_meta = build_document_source_meta(
                filename=filename,
                title=title or filename,
                content_type=content_type,
                size_bytes=len(file_content),
                original_key=s3_key,
                collection_id=str(collection_id),
                row_id=str(row_id),
                qdrant_collection_name=collection.qdrant_collection_name,
                source=source,
                scope=scope,
                tags=tags or [],
            )

            src = Source(
                source_id=doc_id,
                tenant_id=self._tenant_id,
                meta=source_meta,
            )
            self.session.add(src)

            membership = DocumentCollectionMembership(
                tenant_id=self._tenant_id,
                source_id=doc_id,
                collection_id=collection_id,
                collection_row_id=row_id,
            )
            self.session.add(membership)
            await self.session.flush()

            if self.event_publisher:
                status_manager = RAGStatusManager(self.session, self.repo_factory, self.event_publisher)
                embed_models = await status_manager._get_target_models(doc_id)
                await status_manager.initialize_document_statuses(
                    doc_id=doc_id,
                    tenant_id=self._tenant_id,
                    embed_models=embed_models,
                )

            collection.total_rows = (collection.total_rows or 0) + 1
            await CollectionService(self.session).sync_collection_status(collection, persist=False)
            await self.session.flush()
        except Exception:
            await self._cleanup_s3_object(bucket, s3_key)
            raise

        logger.info(
            "collection_document_uploaded",
            extra={
                "collection_id": str(collection_id),
                "doc_id": str(doc_id),
                "row_id": str(row_id),
                "file_name": filename,
            },
        )

        return {
            "document_id": str(doc_id),
            "doc_id": str(doc_id),
            "row_id": str(row_id),
            "collection_id": str(collection_id),
            "status": "uploaded",
            "message": "Document uploaded to collection",
            "artifacts": source_meta["artifacts"],
        }

    async def _get_document_collection(self, collection_id: uuid.UUID) -> Collection:
        svc = CollectionService(self.session)
        collection = await svc.get_by_id(collection_id)
        if not collection:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")
        if collection.collection_type != CollectionType.DOCUMENT.value:
            raise NotDocumentCollectionError(
                f"Collection {collection_id} is not a document collection (type={collection.collection_type})"
            )
        return collection

    async def _upload_to_s3(self, content: bytes, key: str, bucket: str) -> bool:
        import io
        await self._ensure_bucket(bucket)
        file_obj = io.BytesIO(content)
        uploaded = await s3_manager.upload_fileobj(bucket=bucket, key=key, file_obj=file_obj)
        if uploaded:
            logger.info("File uploaded to S3: bucket=%s, key=%s, size=%s", bucket, key, len(content))
        return uploaded

    async def _ensure_bucket(self, bucket: str) -> None:
        client = s3_manager._get_client()
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            try:
                client.create_bucket(Bucket=bucket)
                logger.info("Created S3 bucket for collection uploads: %s", bucket)
            except Exception as exc:
                logger.warning("Failed to create S3 bucket %s: %s", bucket, exc)

    async def _cleanup_s3_object(self, bucket: str, s3_key: str) -> None:
        try:
            deleted = await s3_manager.delete_object(bucket=bucket, key=s3_key)
            if deleted:
                logger.info("Cleaned up orphaned S3 object: s3://%s/%s", bucket, s3_key)
            else:
                logger.warning("Failed to clean up orphaned S3 object: s3://%s/%s", bucket, s3_key)
        except Exception as cleanup_err:
            logger.warning(
                "Cleanup of orphaned S3 object failed for s3://%s/%s: %s",
                bucket,
                s3_key,
                cleanup_err,
            )

    async def _insert_collection_row(
        self,
        collection: Collection,
        file_meta: dict,
        title: Optional[str],
        source_val: Optional[str],
        scope: Optional[str],
        tags: Optional[str],
        meta_fields: Optional[dict] = None,
    ) -> uuid.UUID:
        import json

        row_id = uuid.uuid4()
        values = {"id": row_id}
        extra = meta_fields or {}

        for field_def in collection.fields:
            fname = field_def["name"]
            ftype = field_def["data_type"]

            if fname == "file" or ftype == FieldType.FILE.value:
                values[fname] = json.dumps(file_meta)
            elif fname == "file_name":
                values[fname] = file_meta.get("filename")
            elif fname == "file_content_type":
                values[fname] = file_meta.get("content_type")
            elif fname == "file_size_bytes":
                values[fname] = file_meta.get("size")
            elif fname == "title":
                values[fname] = title
            elif fname == "source":
                values[fname] = source_val
            elif fname == "scope":
                values[fname] = scope
            elif fname == "tags":
                values[fname] = tags
            elif fname in extra:
                values[fname] = extra[fname]
            else:
                values[fname] = None

        columns = ", ".join(values.keys())
        placeholders = ", ".join([f":{k}" for k in values.keys()])
        insert_sql = text(f"INSERT INTO {collection.table_name} ({columns}) VALUES ({placeholders})")
        await self.session.execute(insert_sql, values)

        return row_id
