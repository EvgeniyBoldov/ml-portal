from __future__ import annotations
from typing import Optional
from app.core.config import settings
from app.clients.minio_signer import MinioSigner
from app.storage.paths import content_key

try:
    from minio import Minio
except Exception:
    Minio = None  # type: ignore

class S3Gateway:
    def __init__(self):
        st = settings
        self.bucket = st.S3_BUCKET_RAG
        self.signer = MinioSigner()
        if Minio:
            endpoint = st.S3_ENDPOINT.replace("http://", "").replace("https://", "")
            self.client = Minio(endpoint, access_key=st.S3_ACCESS_KEY, secret_key=st.S3_SECRET_KEY, secure=st.S3_ENDPOINT.startswith("https://"))
        else:
            self.client = None

    def object_name(self, owner_id: str, filename: str, *, content_hash: Optional[str] = None, kind: str = "raw") -> str:
        return content_key(owner_id, filename, content_hash=content_hash, kind=kind)

    async def presign_get(self, object_name: str, *, expires_s: int = 900) -> str:
        return await self.signer.generate(url=object_name, expires_s=expires_s)

    # Note: real put/delete operations require MinIO sdk; keep optional to avoid hard dep
    def put_object(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        if not self.client:
            raise RuntimeError("Minio SDK not installed")
        from io import BytesIO
        self.client.put_object(self.bucket, object_name, BytesIO(data), length=len(data), content_type=content_type)

    def delete_object(self, object_name: str) -> None:
        if not self.client:
            raise RuntimeError("Minio SDK not installed")
        self.client.remove_object(self.bucket, object_name)
