from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal

from minio import Minio
from minio.error import S3Error

from core.config import get_settings

@dataclass
class PresignOptions:
    operation: Literal["get", "put"]
    expiry_seconds: int = 3600
    content_type: Optional[str] = None

class S3Manager:
    """Canonical S3/MinIO manager used by routers/services and s3_links."""
    def __init__(self) -> None:
        s = get_settings()
        endpoint = s.S3_ENDPOINT.replace("http://", "").replace("https://", "")
        self._client = Minio(endpoint, s.S3_ACCESS_KEY, s.S3_SECRET_KEY, secure=bool(s.S3_SECURE))

    def ensure_bucket(self, name: str) -> None:
        if not self._client.bucket_exists(name):
            self._client.make_bucket(name)

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

    def generate_presigned_url(self, *, bucket: str, key: str, options: PresignOptions) -> str:
        self.ensure_bucket(bucket)
        from datetime import timedelta
        expires = timedelta(seconds=options.expiry_seconds)
        if options.operation == "get":
            return self._client.get_presigned_url("GET", bucket, key, expires=expires)
        if options.operation == "put":
            headers = {"Content-Type": options.content_type} if options.content_type else None
            return self._client.get_presigned_url("PUT", bucket, key, expires=expires, response_headers=headers)
        raise ValueError("Unsupported operation for presign")

    async def upload_file(self, bucket: str, key: str, file_obj, content_type: Optional[str] = None) -> None:
        """Upload file to S3/MinIO"""
        self.ensure_bucket(bucket)
        from io import BytesIO
        
        # Read file content
        if hasattr(file_obj, 'read'):
            content = file_obj.read()
        else:
            content = file_obj
        
        # Upload to S3/MinIO
        self._client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=BytesIO(content),
            length=len(content),
            content_type=content_type
        )

    async def delete_file(self, bucket: str, key: str) -> None:
        """Delete file from S3/MinIO"""
        self.delete_object(bucket, key)

s3_manager = S3Manager()
