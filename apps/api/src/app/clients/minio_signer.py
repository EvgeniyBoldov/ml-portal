from __future__ import annotations
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

from app.services.rag_service import PresignedUrlPort
from app.core.config import settings

try:
    from minio import Minio
except Exception:
    Minio = None  # type: ignore

class MinioSigner(PresignedUrlPort):
    def __init__(self):
        st = settings
        self.bucket = st.S3_BUCKET_RAG
        if Minio:
            # Strip scheme for SDK
            endpoint = st.S3_ENDPOINT.replace("http://", "").replace("https://", "")
            self.client = Minio(endpoint, access_key=st.S3_ACCESS_KEY, secret_key=st.S3_SECRET_KEY, secure=st.S3_ENDPOINT.startswith("https://"))
        else:
            self.client = None
            self.public_base = f"{st.S3_PUBLIC_ENDPOINT.rstrip('/')}/{self.bucket}"

    async def generate(self, *, url: str, expires_s: int = 900) -> str:
        # 'url' here is object name inside bucket
        if self.client:
            return self.client.presigned_get_object(self.bucket, url, expires=timedelta(seconds=expires_s))
        # Dev fallback: non-signed public-style URL
        return f"{self.public_base}/{quote(url)}"
