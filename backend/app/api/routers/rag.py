from __future__ import annotations
from typing import Any, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import db_session, get_current_user
from app.services.rag_service import (
    create_upload, list_documents, get_document, delete_document, search,
    start_ingest_chain, start_upload_watch, progress, stats
)

router = APIRouter(prefix="/rag", tags=["rag"])

def _ser_doc(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return row
    out: Dict[str, Any] = {}
    for k in ("id","status","filename","original_name","mime","size","error","tags","created_at","updated_at"):
        if hasattr(row, k):
            v = getattr(row, k)
            if isinstance(v, datetime):
                v = v.isoformat()
            out[k] = str(v) if k == "id" else v
    return out or {"id": str(getattr(row, "id", ""))}

@router.get("")
def list_docs(session: Session = Depends(db_session), user=Depends(get_current_user)):
    rows = list_documents(session)
    return [_ser_doc(r) for r in rows]

@router.get("/{doc_id}")
def get_doc(doc_id: str, session: Session = Depends(db_session), user=Depends(get_current_user)):
    row = get_document(session, doc_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _ser_doc(row)

@router.get("/{doc_id}/progress")
def get_progress(doc_id: str, session: Session = Depends(db_session), user=Depends(get_current_user)):
    return progress(session, doc_id)

@router.get("/stats/summary")
def get_stats(session: Session = Depends(db_session), user=Depends(get_current_user)):
    return stats(session)

@router.delete("/{doc_id}")
def delete_doc(doc_id: str, session: Session = Depends(db_session), user=Depends(get_current_user)):
    ok = delete_document(session, doc_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return {"ok": True}

@router.post("/upload")
def create_upload_url(payload: dict, session: Session = Depends(db_session), user=Depends(get_current_user)):
    meta = create_upload(session, filename=(payload or {}).get("filename"), uploaded_by=user["id"])
    if (payload or {}).get("watch"):
        start_upload_watch(meta["id"], key=meta["key"])  # type: ignore[index]
    if (payload or {}).get("auto_ingest"):
        start_ingest_chain(meta["id"])  # type: ignore[index]
    return meta

@router.post("/search")
def rag_search(payload: dict, session: Session = Depends(db_session), user=Depends(get_current_user)):
    p = payload or {}
    q = p.get("query") or ""
    top_k = int(p.get("top_k") or 5)
    with_snippets = bool(p.get("with_snippets", True))
    offset = int(p.get("offset") or 0)
    doc_id = p.get("doc_id")
    tags = p.get("tags")
    filters = p.get("filters") or {}
    if not tags and isinstance(filters, dict):
        tags = filters.get("tags")
    min_score = filters.get("min_score") if isinstance(filters, dict) else None
    res = search(session, query=q, top_k=top_k, offset=offset, doc_id=doc_id, tags=tags, min_score=min_score, with_snippets=with_snippets)
    return res
