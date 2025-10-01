from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

@dataclass
class PresignOptions:
    operation: Literal["get", "put"]
    expiry_seconds: int = 3600
    content_type: Optional[str] = None

class S3Manager:
    """Canonical S3/MinIO manager used by routers/services and s3_links."""
    def __init__(self) -> None:
        endpoint = getattr(settings, "S3_ENDPOINT", "http://minio:9000")
        endpoint = endpoint.replace("http://", "").replace("https://", "")
        access_key = getattr(settings, "S3_ACCESS_KEY", "minioadmin")
        secret_key = getattr(settings, "S3_SECRET_KEY", "minioadmin")
        # IMPORTANT: use S3_SECURE (not S3_SSL) to align with Settings
        secure = bool(getattr(settings, "S3_SECURE", getattr(settings, "S3_SSL", False)))
        self._client = Minio(endpoint, access_key, secret_key, secure=secure)

    # -------- Bucket utilities

    def ensure_bucket(self, name: str) -> None:
        if not self._client.bucket_exists(name):
            self._client.make_bucket(name)

    # -------- Object utilities

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.stat_object(bucket, key)
            return True
        except S3Error as e:
            if getattr(e, "code", None) in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            raise

    def delete_object(self, bucket: str, key: str) -> None:
        try:
            self._client.remove_object(bucket, key)
        except S3Error as e:
            if getattr(e, "code", None) in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return
            raise

    def get_object_metadata(self, bucket: str, key: str) -> dict:
        """Lightweight metadata wrapper (maps Minio stat to dict)."""
        s = self._client.stat_object(bucket, key)
        return {
            "size": getattr(s, "size", None),
            "etag": getattr(s, "etag", None),
            "content_type": getattr(s, "content_type", None),
            "last_modified": getattr(s, "last_modified", None),
            "version_id": getattr(s, "version_id", None),
        }

    def get_object_bytes(self, bucket: str, key: str) -> bytes:
        resp = self._client.get_object(bucket, key)
        try:
            data = resp.read()
        finally:
            try:
                resp.close()
                resp.release_conn()
            except Exception:
                pass
        return data

    # -------- Presigned URLs

    def generate_presigned_url(
        self,
        *,
        bucket: str,
        key: str,
        options: PresignOptions,
    ) -> str:
        self.ensure_bucket(bucket)
        if options.operation == "get":
            return self._client.get_presigned_url("GET", bucket, key, expires=options.expiry_seconds)
        if options.operation == "put":
            headers = {"Content-Type": options.content_type} if options.content_type else None
            return self._client.get_presigned_url("PUT", bucket, key, expires=options.expiry_seconds, response_headers=headers)
        raise ValueError("Unsupported operation for presign")

# Singleton instance for DI-by-import
s3_manager = S3Manager()
