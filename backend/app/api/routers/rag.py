# app/api/routers/rag.py
"""
RAG роутер по best‑practice:
- Принимаем multipart файл
- Создаём UUID-документ (ORM/Repo)
- Кладём файл в MinIO: rag/{uuid}/origin.{ext}
- Сохраняем метаинфо в БД (оригинальное имя, mime, путь до файла без префикса бакета)
- Триггерим пайплайн (по желанию)
- Скачивание: presigned GET с оригинальным именем
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.config import settings
from app.core.s3_helpers import put_object, presign_get
from app.repositories.rag_repo import RagRepo
from app.services.rag_service import progress, stats, search

router = APIRouter(prefix="/api/rag", tags=["rag"])

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.md', '.rtf', '.odt'}

def _safe_ext(filename: Optional[str]) -> str:
    if not filename or '.' not in filename:
        return ''
    ext = '.' + filename.rsplit('.', 1)[-1].lower()
    return ext if ext in ALLOWED_EXTENSIONS else ''

@router.post("/upload")
async def upload_rag_file(
    file: UploadFile = File(...),
    session: Session = Depends(db_session),
):
    repo = RagRepo(session)
    ext = _safe_ext(file.filename)
    if file.filename and not ext:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    # 1) создаём документ (UUID генерится в базе)
    doc = repo.create_document(
        name=file.filename,
        uploaded_by=None,
        status="uploaded",
        source_mime=file.content_type,
    )
    # 2) ключ origin.{ext} под UUID
    key = f"{doc.id}/origin{ext}"
    # 3) сохраняем в MinIO
    put_object(settings.S3_BUCKET_RAG, key, file.file, content_type=file.content_type)
    # 4) метаданные в БД
    doc.url_file = key
    doc.updated_at = datetime.utcnow()
    session.commit()
    # 5) триггерим пайплайн (если есть upload_watch)
    try:
        from app.tasks.upload_watch import watch as upload_watch
        upload_watch(str(doc.id), key)
    except Exception:
        pass
    return {"id": str(doc.id), "key": key, "status": "uploaded"}

@router.get("/{doc_id}/download")
def download_rag_file(
    doc_id: str,
    kind: str = Query("original", regex="^(original|canonical)$"),
    session: Session = Depends(db_session),
):
    repo = RagRepo(session)
    doc = repo.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")

    bucket = settings.S3_BUCKET_RAG
    if kind == "original":
        key = getattr(doc, "url_file", None)
        if not key:
            raise HTTPException(status_code=404, detail="original_not_ready")
        download_name = doc.name or "document"
        mime = getattr(doc, "source_mime", None)
    else:
        # canonical лежит рядом: rag/{uuid}/canonical.txt
        key = getattr(doc, "url_canonical_file", None) or f"{doc.id}/canonical.txt"
        base = (doc.name or "document").rsplit('.', 1)[0]
        download_name = f"{base}.txt"
        mime = "text/plain"

    url = presign_get(bucket, key, download_name=download_name, mime=mime)
    return {"url": url}

@router.get("/{doc_id}/progress")
def get_rag_progress(
    doc_id: str,
    session: Session = Depends(db_session),
):
    """Получить прогресс обработки RAG документа"""
    return progress(session, doc_id)

@router.get("/stats")
def get_rag_stats(
    session: Session = Depends(db_session),
):
    """Получить статистику RAG документов"""
    return stats(session)

@router.get("/search")
def search_rag(
    query: str,
    top_k: int = 5,
    offset: int = 0,
    doc_id: Optional[str] = None,
    tags: Optional[str] = None,
    sort_by: str = "score_desc",
    session: Session = Depends(db_session),
):
    """Поиск в RAG документах"""
    tags_list = tags.split(",") if tags else None
    return search(session, query, top_k, offset=offset, doc_id=doc_id, tags=tags_list, sort_by=sort_by)
