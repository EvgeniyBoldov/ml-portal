from __future__ import annotations
from typing import BinaryIO
from urllib.parse import urlparse
from minio import Minio
from .config import settings

_client: Minio | None = None

def _mk_client() -> Minio:
    endpoint = settings.S3_ENDPOINT
    secure = False
    netloc = endpoint
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        u = urlparse(endpoint)
        secure = (u.scheme == "https")
        netloc = u.netloc
    return Minio(
        netloc,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
        secure=secure,
    )

def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = _mk_client()
    return _client

def presign_put(bucket: str, key: str, expiry_seconds: int = 3600) -> str:
    return get_minio().presigned_put_object(bucket, key, expires=expiry_seconds)

def ensure_bucket(bucket: str) -> None:
    c = get_minio()
    if not c.bucket_exists(bucket):
        c.make_bucket(bucket)

def put_object(bucket: str, key: str, data: bytes | BinaryIO, length: int | None = None, content_type: str | None = None):
    c = get_minio()
    if hasattr(data, "read"):
        return c.put_object(bucket, key, data, length=length or -1, content_type=content_type)  # type: ignore
    import io
    bio = io.BytesIO(data if isinstance(data, (bytes, bytearray)) else bytes(data))
    return c.put_object(bucket, key, bio, length=len(bio.getvalue()), content_type=content_type)

def get_object(bucket: str, key: str):
    return get_minio().get_object(bucket, key)

def stat_object(bucket: str, key: str):
    return get_minio().stat_object(bucket, key)

def list_buckets():
    return get_minio().list_buckets()
