from __future__ import annotations
from typing import Any, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.api.deps import db_session
from app.services import rag_service

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
def list_docs(session: Session = Depends(db_session)):
	rows = rag_service.list_documents(session)
	items = [_ser_doc(r) for r in rows]
	return {"items": items, "next_cursor": None}

@router.get("/{doc_id}")
def get_doc(doc_id: str, session: Session = Depends(db_session)):
	row = rag_service.get_document(session, doc_id)
	if not row:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
	return _ser_doc(row)

@router.get("/{doc_id}/progress")
def get_progress(doc_id: str, session: Session = Depends(db_session)):
	return rag_service.progress(session, doc_id)

@router.get("/stats/summary")
def get_stats(session: Session = Depends(db_session)):
	return rag_service.stats(session)

@router.delete("/{doc_id}")
def delete_doc(doc_id: str, session: Session = Depends(db_session)):
	ok = rag_service.delete_document(session, doc_id)
	if not ok:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
	return {"ok": True}

# Multipart upload path (frontend uses)
@router.post("/upload")
async def upload_file(
	file: UploadFile = File(...),
	name: str | None = Form(None),
	session: Session = Depends(db_session),
):
	# For now, just create upload entry and return meta; optional: store file to S3
	meta = rag_service.create_upload(session, filename=name or file.filename)
	return meta

@router.post("/search")
def rag_search(payload: dict, session: Session = Depends(db_session)):
	p = payload or {}
	# Frontend sends { text?, top_k?, min_score? }
	q = p.get("text") or p.get("query") or ""
	top_k = int(p.get("top_k") or 5)
	offset = int(p.get("offset") or 0)
	doc_id = p.get("doc_id")
	tags = p.get("tags")
	res = rag_service.search(session, query=q, top_k=top_k, offset=offset, doc_id=doc_id, tags=tags)
	# Map to frontend shape { items: [{ document_id, chunk_id, score, snippet }], next_cursor? }
	items = [{
		"document_id": r.get("doc_id"),
		"chunk_id": r.get("chunk_idx"),
		"score": r.get("score"),
		"snippet": r.get("text"),
	} for r in res.get("results", [])]
	return {"items": items, "next_cursor": res.get("next_offset")}
