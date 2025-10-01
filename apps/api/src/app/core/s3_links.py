from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

from app.adapters.s3_client import S3Manager, s3_manager, PresignOptions
from app.core.config import settings

class S3ContentType(str, Enum):
    PDF = "application/pdf"
    PNG = "image/png"
    JPG = "image/jpeg"
    JSON = "application/json"
    OCTET = "application/octet-stream"

class S3ExpiryPolicy(int, Enum):
    UPLOAD = 15 * 60         # 15 minutes
    DOWNLOAD = 60 * 60       # 1 hour
    ARTIFACT = 24 * 60 * 60  # 24 hours

@dataclass
class S3Link:
    bucket: str
    key: str
    url: str
    content_type: Optional[str]
    expires_in: int
    meta: Dict[str, Any] | None = None

class S3LinkFactory:
    def __init__(self, manager: S3Manager | None = None) -> None:
        self.s3_manager = manager or s3_manager
        # Use buckets from settings (no hardcoded names)
        self.documents_bucket = settings.S3_BUCKET_RAG
        self.artifacts_bucket = settings.S3_BUCKET_ARTIFACTS

    def for_document_upload(self, *, doc_id: str, content_type: str | None = None) -> S3Link:
        key = f"docs/{doc_id}"
        url = self.s3_manager.generate_presigned_url(
            bucket=self.documents_bucket,
            key=key,
            options=PresignOptions(operation="put", expiry_seconds=int(S3ExpiryPolicy.UPLOAD), content_type=content_type),
        )
        return S3Link(bucket=self.documents_bucket, key=key, url=url, content_type=content_type, expires_in=int(S3ExpiryPolicy.UPLOAD), meta={"intent":"upload"})

    def for_document_download(self, *, doc_id: str) -> S3Link:
        key = f"docs/{doc_id}"
        url = self.s3_manager.generate_presigned_url(
            bucket=self.documents_bucket,
            key=key,
            options=PresignOptions(operation="get", expiry_seconds=int(S3ExpiryPolicy.DOWNLOAD)),
        )
        return S3Link(bucket=self.documents_bucket, key=key, url=url, content_type=S3ContentType.OCTET, expires_in=int(S3ExpiryPolicy.DOWNLOAD), meta={"intent":"download"})

    def for_artifact(self, *, job_id: str, filename: str, content_type: str | None = None) -> S3Link:
        key = f"jobs/{job_id}/{filename}"
        url = self.s3_manager.generate_presigned_url(
            bucket=self.artifacts_bucket,
            key=key,
            options=PresignOptions(operation="put", expiry_seconds=int(S3ExpiryPolicy.ARTIFACT), content_type=content_type),
        )
        return S3Link(bucket=self.artifacts_bucket, key=key, url=url, content_type=content_type, expires_in=int(S3ExpiryPolicy.ARTIFACT), meta={"intent":"artifact"})
