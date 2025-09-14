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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Body, Form
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.config import settings
from app.core.s3_helpers import put_object, presign_get
from app.repositories.rag_repo import RagRepo
from app.services.rag_service import progress, stats, search, reprocess_document
from app.models.rag import RagDocuments

router = APIRouter(prefix="/rag", tags=["rag"])

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.md', '.rtf', '.odt'}

def _safe_ext(filename: Optional[str]) -> str:
    if not filename or '.' not in filename:
        return ''
    ext = '.' + filename.rsplit('.', 1)[-1].lower()
    return ext if ext in ALLOWED_EXTENSIONS else ''

@router.post("/upload")
async def upload_rag_file(
    file: UploadFile = File(...),
    tags: str = Form("[]"),  # JSON string of tags
    session: Session = Depends(db_session),
):
    # Валидация размера файла (50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    if hasattr(file, 'size') and file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB")
    
    # Валидация типа файла
    repo = RagRepo(session)
    ext = _safe_ext(file.filename)
    if file.filename and not ext:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    
    # Валидация MIME типа
    if file.content_type and not file.content_type.startswith(('text/', 'application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument')):
        raise HTTPException(status_code=400, detail="Unsupported MIME type")
    
    # Парсим теги
    try:
        import json
        parsed_tags = json.loads(tags) if tags else []
        if not isinstance(parsed_tags, list):
            parsed_tags = []
    except (json.JSONDecodeError, TypeError):
        parsed_tags = []
    
    try:
        # 1) создаём документ (UUID генерится в базе)
        doc = repo.create_document(
            name=file.filename,
            uploaded_by=None,
            status="uploaded",
            source_mime=file.content_type,
            tags=parsed_tags,
        )
        # 2) ключ origin.{ext} под UUID
        key = f"{doc.id}/origin{ext}"
        # 3) сохраняем в MinIO
        put_object(settings.S3_BUCKET_RAG, key, file.file, content_type=file.content_type)
        # 4) метаданные в БД
        doc.url_file = key
        doc.updated_at = datetime.utcnow()
        session.commit()
        # 5) триггерим пайплайн с задержкой (файл должен быть полностью загружен)
        try:
            from app.tasks.upload_watch import watch as upload_watch
            # Запускаем с задержкой 5 секунд, чтобы файл успел загрузиться
            upload_watch.apply_async(args=[str(doc.id)], kwargs={'key': key}, countdown=5)
        except Exception as e:
            # Логируем ошибку, но не прерываем процесс
            print(f"Warning: Failed to trigger upload watch: {e}")
        return {"id": str(doc.id), "key": key, "status": "uploaded", "tags": parsed_tags}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/")
def list_rag_documents(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search in document names"),
    session: Session = Depends(db_session),
):
    repo = RagRepo(session)
    
    # Применяем фильтры
    query = session.query(RagDocuments)
    
    if status:
        query = query.filter(RagDocuments.status == status)
    
    if search:
        query = query.filter(RagDocuments.name.ilike(f"%{search}%"))
    
    # Подсчитываем общее количество
    total = query.count()
    
    # Применяем пагинацию
    offset = (page - 1) * size
    docs = query.offset(offset).limit(size).all()
    
    # Вычисляем метаданные пагинации
    total_pages = (total + size - 1) // size
    has_next = page < total_pages
    has_prev = page > 1
    
    return {
        "items": [{"id": str(doc.id), "name": doc.name, "status": doc.status, "created_at": doc.date_upload.isoformat() if doc.date_upload else None, "url_file": doc.url_file, "url_canonical_file": doc.url_canonical_file, "tags": doc.tags, "progress": None, "updated_at": doc.updated_at.isoformat() if doc.updated_at else None} for doc in docs],
        "pagination": {
            "page": page,
            "size": size,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev
        }
    }

@router.get("/{doc_id}")
def get_rag_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    doc = RagRepo(session).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    return {"id": str(doc.id), "name": doc.name, "status": doc.status, "date_upload": doc.date_upload, "url_file": doc.url_file, "url_canonical_file": doc.url_canonical_file, "tags": doc.tags, "progress": None, "updated_at": doc.updated_at}

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

@router.post("/{doc_id}/archive")
def archive_rag_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    doc = RagRepo(session).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    
    doc.status = "archived"
    doc.updated_at = datetime.utcnow()
    session.commit()
    
    return {"id": str(doc.id), "status": doc.status}

@router.put("/{doc_id}/tags")
def update_rag_document_tags(
    doc_id: str,
    tags: list = Body(...),
    session: Session = Depends(db_session),
):
    doc = RagRepo(session).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc.tags = tags
    doc.updated_at = datetime.utcnow()
    session.commit()
    
    return {"id": str(doc.id), "tags": tags}

@router.delete("/{doc_id}")
def delete_rag_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    doc = RagRepo(session).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    
    # Удаляем файлы из MinIO
    if doc.url_file:
        try:
            from app.core.s3 import get_minio
            client = get_minio()
            client.remove_object(settings.S3_BUCKET_RAG, doc.url_file)
        except Exception:
            pass
    
    if doc.url_canonical_file:
        try:
            from app.core.s3 import get_minio
            client = get_minio()
            client.remove_object(settings.S3_BUCKET_RAG, doc.url_canonical_file)
        except Exception:
            pass
    
    # Удаляем из БД
    session.delete(doc)
    session.commit()
    
    return {"id": str(doc.id), "deleted": True}

@router.post("/search")
def search_rag(
    query: str = Body(..., description="Search query"),
    top_k: int = Body(10, ge=1, le=100),
    min_score: float = Body(0.0, ge=0.0, le=1.0),
    offset: int = Body(0, ge=0),
    session: Session = Depends(db_session),
):
    """Поиск в RAG документах"""
    results = search(session, query, top_k=top_k, offset=offset)
    # Фильтруем по min_score на уровне приложения
    filtered_results = [r for r in results.get("results", []) if r.get("score", 0) >= min_score]
    return {
        "results": filtered_results,
        "next_offset": results.get("next_offset")
    }

@router.post("/{doc_id}/reindex")
def reindex_rag_document(
    doc_id: str,
    session: Session = Depends(db_session),
):
    """Переиндексация RAG документа"""
    repo = RagRepo(session)
    doc = repo.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    success = reprocess_document(session, doc_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start reindexing")
    
    return {"id": doc_id, "status": "reindexing_started"}

@router.post("/reindex")
def reindex_all_rag_documents(
    session: Session = Depends(db_session),
):
    """Массовая переиндексация всех RAG документов"""
    # Получаем все документы со статусом ready
    docs = session.query(RagDocuments).filter(RagDocuments.status == "ready").all()
    
    reindexed_count = 0
    for doc in docs:
        if reprocess_document(session, str(doc.id)):
            reindexed_count += 1
    
    return {"reindexed_count": reindexed_count, "total_documents": len(docs)}
