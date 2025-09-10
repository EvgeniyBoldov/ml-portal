from __future__ import annotations
from celery import shared_task
from datetime import datetime
from app.core.config import settings
from app.core.s3 import get_minio
from app.core.db import SessionLocal
from app.models.rag import RagDocuments
from .shared import log, RetryableError, task_metrics

@shared_task(name="app.tasks.normalize.process", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def process(self, document_id: str, *, source_key: str | None = None) -> dict:
    with task_metrics("normalize.process", "normalize"):
        s3 = get_minio()
        session = SessionLocal()
        try:
            doc = session.get(RagDocuments, document_id)
            if not doc:
                raise RetryableError("document_not_found")
            
            # Заглушка нормализации - просто копируем файл как есть
            src = source_key or (doc.url_file or f"{doc.id}/source.bin")
            dst = f"{doc.id}/document.json"
            
            try:
                # Получаем исходный файл
                obj = s3.get_object(settings.S3_BUCKET_RAW, src)
                content = obj.read()
                
                # Простая заглушка - если это текстовый файл, читаем как текст
                try:
                    text_content = content.decode('utf-8')
                    # Создаем JSON с текстом
                    import json
                    normalized_data = {"text": text_content, "type": "text", "original_filename": doc.name}
                    json_content = json.dumps(normalized_data, ensure_ascii=False).encode('utf-8')
                except UnicodeDecodeError:
                    # Если не текстовый файл, сохраняем как бинарный
                    import json
                    normalized_data = {"type": "binary", "original_filename": doc.name, "size": len(content)}
                    json_content = json.dumps(normalized_data, ensure_ascii=False).encode('utf-8')
                
                # Сохраняем нормализованный файл
                s3.put_object(settings.S3_BUCKET_CANONICAL, dst, json_content, length=len(json_content))
                
            except Exception as e:
                log.error(f"Error processing file {src}: {e}")
                # Создаем пустой файл в случае ошибки
                from io import BytesIO
                s3.put_object(settings.S3_BUCKET_CANONICAL, dst, BytesIO(b'{"text": "", "type": "error"}'), length=2)
            
            doc.url_canonical_file = dst
            doc.status = "chunking"
            doc.updated_at = datetime.utcnow()
            session.commit()
            return {"document_id": str(doc.id), "status": doc.status, "canonical_key": dst}
        finally:
            session.close()
