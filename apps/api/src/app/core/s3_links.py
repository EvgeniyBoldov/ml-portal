from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
from minio import Minio
from .config import get_settings

class S3ContentType:
    OCTET = "application/octet-stream"
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"

@dataclass
class S3Link:
    url: str
    bucket: str
    key: str
    content_type: str
    expires_in: int
    meta: Dict[str, Any]

class S3LinkFactory:
    def __init__(self) -> None:
        s = get_settings()
        endpoint = s.S3_ENDPOINT.replace("http://", "").replace("https://", "")
        self._client = Minio(endpoint, s.S3_ACCESS_KEY, s.S3_SECRET_KEY, secure=bool(s.S3_SECURE))
        self._s = s

    def _presign(self, method: str, bucket: str, key: str, *, content_type: Optional[str] = None, expires: int = 3600) -> str:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
        if method == "PUT":
            headers = {"Content-Type": content_type} if content_type else None
            return self._client.get_presigned_url("PUT", bucket, key, expires=expires, response_headers=headers)
        return self._client.get_presigned_url("GET", bucket, key, expires=expires)

    def for_document_upload(self, *, doc_id: str, tenant_id: str, content_type: str = S3ContentType.OCTET, expires_in: int = 3600) -> S3Link:
        key = f"tenants/{tenant_id}/docs/{doc_id}"
        url = self._presign("PUT", self._s.S3_BUCKET_RAG, key, content_type=content_type, expires=expires_in)
        return S3Link(url=url, bucket=self._s.S3_BUCKET_RAG, key=key, content_type=content_type, expires_in=expires_in, meta={"max_bytes": self._s.UPLOAD_MAX_BYTES})

    def for_artifact(self, *, job_id: str, filename: str, tenant_id: str, content_type: Optional[str] = None, expires_in: int = 3600) -> S3Link:
        key = f"tenants/{tenant_id}/artifacts/{job_id}/{filename}"
        ct = content_type or S3ContentType.OCTET
        url = self._presign("PUT", self._s.S3_BUCKET_ARTIFACTS, key, content_type=ct, expires=expires_in)
        return S3Link(url=url, bucket=self._s.S3_BUCKET_ARTIFACTS, key=key, content_type=ct, expires_in=expires_in, meta={"max_bytes": self._s.UPLOAD_MAX_BYTES})
