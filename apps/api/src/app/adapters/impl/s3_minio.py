from typing import Optional
from io import BytesIO
from minio import Minio
from minio.error import S3Error
from starlette.concurrency import run_in_threadpool
from ..exceptions.base import UpstreamError
from ..interfaces.object_storage import ObjectStorage
from ...core.config import get_settings

class MinioStorage(ObjectStorage):
    def __init__(self, endpoint: Optional[str] = None, access_key: Optional[str] = None, secret_key: Optional[str] = None, secure: Optional[bool] = None):
        s = get_settings()
        self._client = Minio(
            endpoint or s.S3_ENDPOINT,
            access_key=access_key or s.S3_ACCESS_KEY,
            secret_key=secret_key or s.S3_SECRET_KEY,
            secure=s.S3_SECURE if secure is None else secure,
        )

    async def put(self, bucket: str, key: str, data: bytes, *, content_type: str | None = None) -> None:
        stream = BytesIO(data)
        try:
            await run_in_threadpool(
                self._client.put_object,
                bucket,
                key,
                data=stream,
                length=len(data),
                content_type=content_type,
            )
        except S3Error as e:
            raise UpstreamError(str(e))

    async def get(self, bucket: str, key: str) -> bytes:
        try:
            obj = await run_in_threadpool(self._client.get_object, bucket, key)
            try:
                return obj.read()
            finally:
                obj.close()
                obj.release_conn()
        except S3Error as e:
            raise UpstreamError(str(e))

    async def delete(self, bucket: str, key: str) -> None:
        try:
            await run_in_threadpool(self._client.remove_object, bucket, key)
        except S3Error as e:
            raise UpstreamError(str(e))

    async def presign_get(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        try:
            return await run_in_threadpool(self._client.presigned_get_object, bucket, key, expires=expires_in)
        except S3Error as e:
            raise UpstreamError(str(e))
