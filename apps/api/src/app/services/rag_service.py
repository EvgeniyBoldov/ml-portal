# app/services/rag_service.py
# Best-practice naming for RAG + analysis:
# - store original filename only in DB metadata
# - in MinIO use doc_id as "directory":
#     RAW:       {doc_id}/source{ext}
#     CANONICAL: {doc_id}/document.json
#     PREVIEW:   {doc_id}/preview/page-{n}.png
#
# Also adds dual delete modes:
# - soft delete: sets status='archived' (keeps data)
# - hard delete: Celery task purges MinIO objects + Qdrant points + DB rows

from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.s3 import presign_put
from app.core.metrics import rag_ingest_started_total
from app.repositories.rag_repo import RagRepo
from app.tasks.normalize import process as normalize_process
from app.tasks.chunk import split as chunk_split
from app.tasks.embed import compute as embed_compute
from app.tasks.index import finalize as index_finalize
from app.tasks.upload_watch import watch as start_upload_watch
from app.tasks.delete import hard_delete as hard_delete_task
from app.models.rag import RagDocuments, RagChunks
from . import clients

# White-list of allowed extensions
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.md', '.rtf', '.odt'}


def _safe_ext(filename: Optional[str]) -> str:
    if not filename or '.' not in filename:
        return ''
    ext = '.' + filename.rsplit('.', 1)[-1].lower()
    return ext if ext in ALLOWED_EXTENSIONS else ''


def create_upload(session: Session, filename: str, uploaded_by: Optional[str] = None) -> Dict[str, Any]:
    """Create a document record and return a presigned PUT URL for the RAG upload.
    New naming logic: rag/{doc_id}/origin.{ext} for original files
    """
    file_ext = _safe_ext(filename)
    if filename and file_ext == '':
        raise ValueError(f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    repo = RagRepo(session)
    # Persist original name in DB; storage key does NOT depend on it
    doc = repo.create_document(name=filename, uploaded_by=uploaded_by, status="uploaded")

    # New naming: rag/{doc_id}/origin.{ext}
    key = f"{doc.id}/origin{file_ext}"
    put_url = presign_put(settings.S3_BUCKET_RAG, key, 3600)

    # Save storage key for downstream tasks
    doc.url_file = key
    doc.updated_at = datetime.utcnow()
    session.commit()

    # Don't start watcher yet - wait for file to be uploaded via presigned URL
    # start_upload_watch(str(doc.id), key=key)
    
    # Запускаем цепочку обработки сразу после создания документа
    start_ingest_chain(str(doc.id))

    return {"id": str(doc.id), "put_url": put_url, "key": key}


def delete_document(session: Session, doc_id: str, *, hard: bool = False) -> bool:
    """Two deletion modes:
    - soft (default): mark as archived (keeps MinIO/Qdrant/DB children intact)
    - hard: schedule full purge task that removes MinIO objects, Qdrant points and DB rows
    """
    repo = RagRepo(session)
    doc = repo.get(doc_id)
    if not doc:
        return False

    if hard:
        # Fire-and-forget Celery task
        hard_delete_task.delay(str(doc.id))
        return True

    # Soft delete: archive only (no storage/Qdrant changes)
    doc.status = "archived"
    doc.updated_at = datetime.utcnow()
    session.commit()
    return True


def list_documents(session: Session, limit: int = 50):
    return RagRepo(session).list(limit=limit)


def get_document(session: Session, doc_id):
    return RagRepo(session).get(doc_id)


def start_ingest_chain(doc_id: str) -> None:
    rag_ingest_started_total.inc()
    # Используем правильный синтаксис для Celery цепочки
    from celery import chain
    chain(
        normalize_process.s(doc_id),
        chunk_split.s(),
        embed_compute.s(),
        index_finalize.s()
    ).apply_async()


def search(session: Session, query: str, top_k: int = 5, *, offset: int = 0, doc_id: Optional[str] = None, tags: Optional[list] = None, sort_by: str = "score_desc") -> Dict[str, Any]:
    try:
        vectors = clients.embed_texts([query])
        if not vectors:
            return {"results": [], "next_offset": None}
        vec = vectors[0]
        hits = clients.qdrant_search(vec, top_k=top_k, offset=offset, doc_id=doc_id, tags=tags, sort_by=sort_by)
        out = []
        for h in hits:
            payload = h.get("payload") or {}
            out.append({
                "score": h["score"],
                "text": payload.get("text"),
                "doc_id": payload.get("document_id"),
                "chunk_idx": payload.get("chunk_idx"),
                "tags": payload.get("tags") or [],
            })
        next_offset = offset + len(out) if len(out) == top_k else None
        return {"results": out, "next_offset": next_offset}
    except Exception as e:
        # Если сервисы эмбеддингов недоступны, возвращаем пустой результат
        return {"results": [], "next_offset": None, "error": "Embedding service unavailable"}


def progress(session: Session, doc_id: str) -> Dict[str, Any]:
    from sqlalchemy import func
    doc = session.get(RagDocuments, doc_id)
    if not doc:
        return {"id": doc_id, "status": "not_found"}
    chunks_total = session.query(func.count(RagChunks.id)).filter(RagChunks.document_id == doc.id).scalar() or 0
    vectors_total = clients.qdrant_count_by_doc(str(doc.id))
    return {
        "id": str(doc.id),
        "status": doc.status,
        "chunks_total": int(chunks_total),
        "vectors_total": int(vectors_total),
        "updated_at": (doc.updated_at.isoformat() if getattr(doc, "updated_at", None) else None),
    }


def stats(session: Session) -> Dict[str, Any]:
    from sqlalchemy import func
    rows = session.query(RagDocuments.status, func.count(RagDocuments.id)).group_by(RagDocuments.status).all()
    by_status = {k or "unknown": int(v or 0) for k, v in rows}
    total_docs = sum(by_status.values())
    return {"total_docs": total_docs, "by_status": by_status}


def get_download_url(session: Session, doc_id: str, file_type: str = "original") -> str:
    """Get download URL for a document file."""
    doc = RagRepo(session).get(doc_id)
    if not doc:
        raise ValueError("Document not found")
    
    if file_type == "original":
        key = doc.url_file
        bucket = settings.S3_BUCKET_RAG
    elif file_type == "canonical":
        key = doc.url_canonical_file
        bucket = settings.S3_BUCKET_RAG
    elif file_type == "preview":
        key = doc.url_preview_file
        bucket = settings.S3_BUCKET_RAG
    else:
        raise ValueError("Invalid file type")
    
    if not key:
        raise ValueError(f"{file_type} file not available")
    
    return presign_put(bucket, key, 3600)


def reprocess_document(session: Session, doc_id: str) -> bool:
    """Reprocess a document through the entire pipeline."""
    doc = RagRepo(session).get(doc_id)
    if not doc:
        return False
    
    # Reset status and clear previous results
    doc.status = "uploaded"
    doc.url_canonical_file = None
    doc.updated_at = datetime.utcnow()
    session.commit()
    
    # Start the processing chain
    start_ingest_chain(str(doc.id))
    return True
