"""
TemplateUploadService — upload a template file into a template collection.

Flow:
1. Validate collection is TEMPLATE
2. Save file to S3
3. Create a row in the collection dynamic table with file metadata
4. Async analysis tasks fill description + schema later
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import io
from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.core.exceptions import CollectionDocumentUploadError, InvalidSchemaError
from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType
from app.services.collection.row_service import CollectionRowService
from app.storage.paths import calculate_file_checksum, get_origin_path

logger = get_logger(__name__)


class TemplateUploadService:
    def __init__(
        self,
        session: AsyncSession,
        row_service: Optional[CollectionRowService] = None,
    ):
        self.session = session
        self.row_service = row_service or CollectionRowService(session)

    async def upload_template(
        self,
        collection: Collection,
        file_content: bytes,
        filename: str,
        content_type: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> dict:
        if collection.collection_type != CollectionType.TEMPLATE.value:
            raise InvalidSchemaError("Collection must be of type 'template'")

        file_id = uuid.uuid4()
        settings = get_settings()
        file_checksum = calculate_file_checksum(file_content)
        s3_key = get_origin_path(collection.tenant_id, file_id, filename, file_checksum)
        bucket = settings.S3_BUCKET_RAG  # reuse RAG bucket for template storage
        uploaded = await self._upload_to_s3(file_content, s3_key, bucket)
        if not uploaded:
            raise CollectionDocumentUploadError(f"Failed to upload file to s3://{bucket}/{s3_key}")

        file_meta = {
            "s3_key": s3_key,
            "bucket": bucket,
            "filename": filename,
            "content_type": content_type or "application/octet-stream",
            "size": len(file_content),
            "file_id": str(file_id),
        }

        payload = {
            "file": file_meta,
            "title": filename,
            "source": f"s3://{bucket}/{s3_key}",
            "status": "uploaded",
        }

        # Remove None values for optional fields so coercion doesn't fail
        payload = {k: v for k, v in payload.items() if v is not None}

        created_row = await self.row_service.create_row(collection, payload)

        return {
            "row_id": str(created_row["id"]),
            "collection_id": str(collection.id),
            "file_id": str(file_id),
            "title": payload.get("title"),
            "source": payload.get("source"),
            "status": payload.get("status"),
            "message": "Template uploaded successfully",
        }

    async def _upload_to_s3(self, content: bytes, key: str, bucket: str) -> bool:
        try:
            file_obj = io.BytesIO(content)
            uploaded = await s3_manager.upload_fileobj(bucket=bucket, key=key, file_obj=file_obj)
            if uploaded:
                logger.info("File uploaded to S3: bucket=%s, key=%s, size=%s", bucket, key, len(content))
            return uploaded
        except Exception as exc:
            logger.error(f"S3 upload failed for {bucket}/{key}: {exc}")
            return False
