# app/api/routers/analyze.py
"""
Аналитический роутер — те же правила, другой бакет:
- analysis/{uuid}/origin.{ext}, рядом canonical.txt и preview/*
- Метаданные в БД; скачивание presigned GET с оригинальным именем
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.config import settings
from app.core.s3_helpers import put_object, presign_get
from app.repositories.analyze_repo import AnalyzeRepo

router = APIRouter(prefix="/analyze", tags=["analyze"])

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.md', '.rtf', '.odt'}

def _safe_ext(filename: Optional[str]) -> str:
    if not filename or '.' not in filename:
        return ''
    ext = '.' + filename.rsplit('.', 1)[-1].lower()
    return ext if ext in ALLOWED_EXTENSIONS else ''

@router.post("/upload")
async def upload_analysis_file(
    file: UploadFile = File(...),
    session: Session = Depends(db_session),
):
    repo = AnalyzeRepo(session)
    ext = _safe_ext(file.filename)
    if file.filename and not ext:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    doc = repo.create_document(
        uploaded_by=None,
        status="queued",
    )
    key = f"{doc.id}/origin{ext}"
    put_object(settings.S3_BUCKET_ANALYSIS, key, file.file, content_type=file.content_type)

    doc.url_file = key
    doc.updated_at = datetime.utcnow()
    session.commit()

    try:
        from app.tasks.upload_watch import watch as upload_watch
        upload_watch(str(doc.id), key)
    except Exception:
        pass

    return {"id": str(doc.id), "key": key, "status": "uploaded"}

@router.get("/")
def list_analysis_documents(
    session: Session = Depends(db_session),
):
    repo = AnalyzeRepo(session)
    docs = repo.list()
    return {"items": [{"id": str(doc.id), "status": doc.status, "date_upload": doc.date_upload, "url_file": doc.url_file, "url_canonical_file": doc.url_canonical_file, "result": doc.result, "error": doc.error, "updated_at": doc.updated_at} for doc in docs]}

@router.get("/documents")
def legacy_documents_endpoint():
    print("DEBUG: legacy_documents_endpoint called")
    raise HTTPException(status_code=404, detail="Endpoint moved. Use /api/analyze/ instead.")

@router.get("/document/{doc_id}")
def get_analysis_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    doc = AnalyzeRepo(session).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    return {"id": str(doc.id), "status": doc.status, "date_upload": doc.date_upload, "url_file": doc.url_file, "url_canonical_file": doc.url_canonical_file, "result": doc.result, "error": doc.error, "updated_at": doc.updated_at}

@router.get("/document/{doc_id}/download")
def download_analysis_file(
    doc_id: str,
    kind: str = Query("original", regex="^(original|canonical)$"),
    session: Session = Depends(db_session),
):
    doc = AnalyzeRepo(session).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")

    bucket = settings.S3_BUCKET_ANALYSIS
    if kind == "original":
        key = getattr(doc, "url_file", None)
        if not key:
            raise HTTPException(status_code=404, detail="original_not_ready")
        download_name = "document"
        mime = getattr(doc, "source_mime", None)
    else:
        key = getattr(doc, "url_canonical_file", None) or f"{doc.id}/canonical.txt"
        base = "document"
        download_name = f"{base}.txt"
        mime = "text/plain"

    url = presign_get(bucket, key, download_name=download_name, mime=mime)
    return {"url": url}
