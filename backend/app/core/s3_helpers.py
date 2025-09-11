# app/core/s3_helpers.py
from __future__ import annotations
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

from app.core.config import settings
from app.core.s3 import get_minio  # ожидается, что он уже есть в вашем проекте

def put_object(bucket: str, key: str, data, *, content_type: Optional[str] = None, part_size: int = 10 * 1024 * 1024):
    """
    Безопасная загрузка потока в MinIO.
    Использует multipart (length=-1), если длина неизвестна (UploadFile.file).
    """
    client = get_minio()
    return client.put_object(bucket, key, data, length=-1, part_size=part_size, content_type=content_type)

def _content_disposition(filename: str) -> str:
    # RFC 5987 filename*
    return f"attachment; filename*=UTF-8''{quote(filename)}"

def presign_get(bucket: str, key: str, *, seconds: int = 3600, download_name: Optional[str] = None, mime: Optional[str] = None) -> str:
    """
    Генерирует presigned GET URL. Добавляет правильный Content-Disposition и MIME.
    Если настроен публичный endpoint, подменяет на него URL.
    """
    client = get_minio()
    headers = {}
    if download_name:
        headers["response-content-disposition"] = _content_disposition(download_name)
    if mime:
        headers["response-content-type"] = mime
    url = client.presigned_get_object(bucket, key, expires=timedelta(seconds=seconds), response_headers=headers)
    if getattr(settings, "S3_PUBLIC_ENDPOINT", None) and settings.S3_PUBLIC_ENDPOINT != settings.S3_ENDPOINT:
        url = url.replace(settings.S3_ENDPOINT.rstrip("/"), settings.S3_PUBLIC_ENDPOINT.rstrip("/"))
    return url
