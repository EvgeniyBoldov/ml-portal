from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.s3 import presign_put
from app.core.config import settings
from app.core.metrics import rag_ingest_started_total
from app.repositories.rag_repo import RagRepo
from app.tasks.normalize import process as normalize_process
from app.tasks.chunk import split as chunk_split
from app.tasks.embed import compute as embed_compute
from app.tasks.index import finalize as index_finalize
from app.tasks.upload_watch import watch as upload_watch
from app.models.rag import RagDocuments, RagChunks
from . import clients

def create_upload(session: Session, filename: str, uploaded_by=None) -> Dict[str, Any]:
    repo = RagRepo(session)
    doc = repo.create_document(name=filename, uploaded_by=uploaded_by, status="uploaded")
    key = f"{doc.id}/{filename}"
    put_url = presign_put(settings.S3_BUCKET_RAW, key, 3600)
    doc.url_file = key
    doc.updated_at = datetime.utcnow()
    session.commit()
    return {"id": str(doc.id), "put_url": put_url, "key": key}

def list_documents(session: Session, limit: int = 50):
    return RagRepo(session).list(limit=limit)

def get_document(session: Session, doc_id):
    return RagRepo(session).get(doc_id)

def delete_document(session: Session, doc_id):
    repo = RagRepo(session); doc = repo.get(doc_id)
    if not doc: return False
    repo.delete(doc); return True

def start_ingest_chain(doc_id: str) -> None:
    rag_ingest_started_total.inc()
    chain = normalize_process.s(doc_id) | chunk_split.s() | embed_compute.s() | index_finalize.s()
    chain.apply_async()

def start_upload_watch(doc_id: str, key: str) -> None:
    upload_watch.delay(doc_id, key=key)

def search(session: Session, query: str, top_k: int = 5, *, offset: int = 0, doc_id: Optional[str] = None, tags: Optional[List[str]] = None, sort_by: str = "score_desc") -> Dict[str, Any]:
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

def progress(session: Session, doc_id: str) -> Dict[str, Any]:
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
    rows = session.query(RagDocuments.status, func.count(RagDocuments.id)).group_by(RagDocuments.status).all()
    by_status = {k or "unknown": int(v or 0) for k, v in rows}
    total_docs = sum(by_status.values())
    return {"total_docs": total_docs, "by_status": by_status}
