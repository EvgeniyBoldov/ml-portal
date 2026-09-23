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
from datetime import date, datetime
from typing import Any, Optional, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType, FieldType
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source, DocumentCollectionMembership
from app.models.memory_scope import DocumentMemoryScope
from app.repositories.factory import AsyncRepositoryFactory
from app.services.collection_service import CollectionService
from app.core.exceptions import CollectionNotFoundError, CollectionDocumentUploadError, NotDocumentCollectionError
from app.services.document_artifacts import build_document_source_meta
from app.services.memory_scope_catalog import resolve_memory_scopes
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
        memory_enabled: Optional[bool] = None,
        project_keys: Optional[List[str]] = None,
        memory_scope_keys: Optional[List[str]] = None,
    ) -> dict:
        """Upload a file into a document collection and persist RAG bookkeeping."""
        collection = await self._get_document_collection(collection_id)
        selected_scope_keys = [*(memory_scope_keys or []), *(f"project.{key}" for key in (project_keys or []))]
        selected_scopes = await resolve_memory_scopes(self.session, selected_scope_keys)
        normalized_meta_fields = self._validate_document_metadata(collection, meta_fields or {})
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

            row_insert_result = await self._insert_collection_row(
                collection=collection,
                file_meta=file_meta,
                title=title or filename,
                source_val=source,
                scope=scope,
                tags=",".join(tags) if tags else None,
                meta_fields=normalized_meta_fields,
            )
            if isinstance(row_insert_result, tuple):
                row_id, prefilter = row_insert_result
            else:
                row_id, prefilter = row_insert_result, {}

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
            for selected_scope in selected_scopes:
                self.session.add(DocumentMemoryScope(
                    document_id=doc_id, scope_id=selected_scope.id, method="explicit",
                ))

            source_meta = build_document_source_meta(
                filename=filename,
                title=title or filename,
                content_type=content_type,
                size_bytes=len(file_content),
                original_key=s3_key,
                collection_id=str(collection_id),
                row_id=str(row_id),
                qdrant_collection_name=collection.qdrant_collection_name,
                prefilter=prefilter,
                source=source,
                scope=scope,
                tags=tags or [],
                memory_enabled=bool(getattr(collection, "memory_enabled", False)) if memory_enabled is None else memory_enabled,
                memory_policy="collection" if memory_enabled is None else "explicit",
                project_keys=project_keys,
                memory_scope_keys=[item.key for item in selected_scopes],
            )
            # Only declared fields are allowed to affect retrieval/prompt
            # context.  Store the exact projection alongside the source so it
            # remains stable even if the dynamic collection row is edited.
            collection_fields = {field.get("name"): field for field in (collection.fields or [])}
            retrieval_fields = {
                name: value for name, value in normalized_meta_fields.items()
                if collection_fields.get(name, {}).get("used_in_retrieval") and value is not None
            }
            prompt_fields = {
                name: value for name, value in normalized_meta_fields.items()
                if collection_fields.get(name, {}).get("used_in_prompt_context") and value is not None
            }
            source_meta["collection"]["retrieval_fields"] = retrieval_fields
            source_meta["collection"]["prompt_fields"] = prompt_fields

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

    @staticmethod
    def _validate_document_metadata(collection: Collection, raw: dict[str, Any]) -> dict[str, Any]:
        """Reject unknown/invalid user fields before creating external artifacts."""
        if not isinstance(raw, dict):
            raise CollectionDocumentUploadError("meta_fields must be an object")
        fields = {str(field.get("name")): field for field in (collection.fields or []) if field.get("name")}
        unknown = sorted(set(raw) - set(fields))
        if unknown:
            raise CollectionDocumentUploadError(f"Unknown document metadata fields: {', '.join(unknown)}")

        derived = {"file", "file_name", "file_content_type", "file_size_bytes", "title", "source", "scope", "tags"}
        result: dict[str, Any] = {}
        for name, field in fields.items():
            value = raw.get(name)
            if value is None:
                if field.get("required") and name not in derived:
                    raise CollectionDocumentUploadError(f"Required document metadata field is missing: {name}")
                continue
            field_type = field.get("data_type")
            try:
                if field_type == FieldType.INTEGER.value:
                    if isinstance(value, bool):
                        raise ValueError()
                    value = int(value)
                elif field_type == FieldType.FLOAT.value:
                    if isinstance(value, bool):
                        raise ValueError()
                    value = float(value)
                elif field_type == FieldType.BOOLEAN.value:
                    if isinstance(value, str):
                        lowered = value.strip().lower()
                        if lowered not in {"true", "false"}:
                            raise ValueError()
                        value = lowered == "true"
                    elif not isinstance(value, bool):
                        raise ValueError()
                elif field_type in {FieldType.STRING.value, FieldType.TEXT.value, FieldType.ENUM.value}:
                    if not isinstance(value, str):
                        raise ValueError()
                    allowed = field.get("enum_values") or field.get("options")
                    if field_type == FieldType.ENUM.value and isinstance(allowed, list) and value not in allowed:
                        raise ValueError()
                elif field_type == FieldType.DATE.value:
                    value = date.fromisoformat(str(value)).isoformat()
                elif field_type == FieldType.DATETIME.value:
                    value = datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
                elif field_type == FieldType.JSON.value and not isinstance(value, (dict, list)):
                    raise ValueError()
            except (TypeError, ValueError):
                raise CollectionDocumentUploadError(f"Invalid value for document metadata field '{name}'") from None
            result[name] = value
        return result

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
    ) -> tuple[uuid.UUID, dict]:
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

        prefilter: dict = {}
        for field_def in collection.fields:
            fname = field_def.get("name")
            if not fname or not field_def.get("filterable", False):
                continue
            ftype = field_def.get("data_type")
            if ftype == FieldType.FILE.value:
                continue
            val = values.get(fname)
            if val is None:
                continue
            if isinstance(val, (str, int, float, bool)):
                prefilter[fname] = val
            elif isinstance(val, list):
                scalar_items = [x for x in val if isinstance(x, (str, int, float, bool))]
                if scalar_items:
                    prefilter[fname] = scalar_items

        return row_id, prefilter
