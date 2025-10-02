from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException
from app.adapters.s3_client import s3_manager, PresignOptions
from app.core.config import get_settings
from app.core.s3_links import S3ContentType

router = APIRouter(tags=["rag"])

@router.post("/upload/presign")
def presign_rag_upload(body: dict[str, Any]) -> dict:
    doc_id = body.get("document_id")
    if not doc_id:
        raise HTTPException(status_code=400, detail="document_id is required")
    content_type = body.get("content_type", S3ContentType.OCTET)
    key = f"docs/{doc_id}"
    s = get_settings()
    url = s3_manager.generate_presigned_url(
        bucket=s.S3_BUCKET_RAG,
        key=key,
        options=PresignOptions(operation="put", expiry_seconds=3600, content_type=content_type),
    )
    return {"presigned_url": url, "bucket": s.S3_BUCKET_RAG, "key": key, "content_type": content_type, "expires_in": 3600}
