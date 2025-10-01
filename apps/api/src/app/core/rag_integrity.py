from __future__ import annotations
from typing import Optional
from app.adapters.s3_client import s3_manager
from app.core.config import settings

def object_exists(bucket: str, key: str) -> bool:
    return s3_manager.exists(bucket, key)

def object_metadata(bucket: str, key: str) -> dict:
    return s3_manager.get_object_metadata(bucket, key)

def object_bytes(bucket: str, key: str) -> bytes:
    return s3_manager.get_object_bytes(bucket, key)

def build_rag_key(doc_id: str) -> str:
    return f"docs/{doc_id}"

def ensure_rag_document_present(doc_id: str) -> dict:
    bucket = settings.S3_BUCKET_RAG
    key = build_rag_key(doc_id)
    if not object_exists(bucket, key):
        return {"ok": False, "reason": "missing"}
    meta = object_metadata(bucket, key)
    return {"ok": True, "meta": meta}
