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
from app.core.s3 import s3_manager
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
    s3_manager.put_object(settings.S3_BUCKET_ANALYSIS, key, file.file, content_type=file.content_type)

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
    return {"items": [{"id": str(doc.id), "status": doc.status, "created_at": doc.date_upload.isoformat() if doc.date_upload else None, "url_file": doc.url_file, "url_canonical_file": doc.url_canonical_file, "result": doc.result, "error": doc.error, "updated_at": doc.updated_at.isoformat() if doc.updated_at else None} for doc in docs]}

@router.get("/{doc_id}")
def get_analysis_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    """Получить информацию о документе анализа"""
    repo = AnalyzeRepo(session)
    doc = repo.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "id": str(doc.id),
        "status": doc.status,
        "created_at": doc.date_upload.isoformat() if doc.date_upload else None,
        "url_file": doc.url_file,
        "url_canonical_file": doc.url_canonical_file,
        "result": doc.result,
        "error": doc.error,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
    }

@router.get("/{doc_id}/download")
def download_analysis_file(
    doc_id: str,
    kind: str = Query("original", description="File type: original or canonical"),
    session: Session = Depends(db_session),
):
    """Скачать файл анализа"""
    repo = AnalyzeRepo(session)
    doc = repo.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if kind == "canonical" and not doc.url_canonical_file:
        raise HTTPException(status_code=404, detail="Canonical file not available")
    
    file_key = doc.url_canonical_file if kind == "canonical" else doc.url_file
    if not file_key:
        raise HTTPException(status_code=404, detail="File not found")
    
    url = s3_manager.presign_get(settings.S3_BUCKET_ANALYSIS, file_key, expires_in=3600)
    return {"url": url}

@router.delete("/{doc_id}")
def delete_analysis_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    """Удалить документ анализа"""
    repo = AnalyzeRepo(session)
    doc = repo.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Удаляем из S3
    if doc.url_file:
        try:
            from app.core.s3 import get_minio
            minio = get_minio()
            minio.remove_object(settings.S3_BUCKET_ANALYSIS, doc.url_file)
        except Exception:
            pass  # Игнорируем ошибки удаления из S3
    
    if doc.url_canonical_file:
        try:
            from app.core.s3 import get_minio
            minio = get_minio()
            minio.remove_object(settings.S3_BUCKET_RAG, doc.url_canonical_file)
        except Exception:
            pass
    
    # Удаляем из БД
    session.delete(doc)
    session.commit()
    
    return {"id": str(doc.id), "deleted": True}

@router.post("/{doc_id}/reanalyze")
def reanalyze_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    """Повторно проанализировать документ"""
    repo = AnalyzeRepo(session)
    doc = repo.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Сбрасываем статус и запускаем заново
    doc.status = "queued"
    doc.result = None
    doc.error = None
    doc.updated_at = datetime.utcnow()
    session.commit()
    
    # Запускаем задачу анализа
    try:
        from app.tasks.bg_tasks_enhanced import analyze_document
        analyze_document.delay(str(doc.id))
    except Exception as e:
        doc.status = "error"
        doc.error = f"Failed to start reanalysis: {str(e)}"
        session.commit()
        raise HTTPException(status_code=500, detail="Failed to start reanalysis")
    
    return {"id": str(doc.id), "status": "reanalysis_started"}