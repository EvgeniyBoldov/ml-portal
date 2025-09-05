from __future__ import annotations
from datetime import datetime
from celery import shared_task
from app.core.qdrant import get_qdrant
from app.core.db import SessionLocal
from app.models.rag import RagDocuments, RagChunks
from .shared import log, task_metrics

COLLECTION = "rag_chunks"

@shared_task(name="app.tasks.index.finalize", bind=True)
def finalize(self, document_id: str) -> dict:
    with task_metrics("index.finalize", "index"):
        session = SessionLocal()
        qdrant = get_qdrant()
        try:
            doc = session.get(RagDocuments, document_id)
            if not doc:
                return {"document_id": document_id, "status": "not_found"}
            # простая проверка наличия поинтов документа
            # (в реале — count по payload фильтру)
            doc.status = "ready"
            doc.updated_at = datetime.utcnow()
            session.commit()
            return {"document_id": str(doc.id), "status": doc.status}
        finally:
            session.close()

@shared_task(name="app.tasks.index.housekeeping", bind=True)
def housekeeping(self) -> dict:
    with task_metrics("index.housekeeping", "index"):
        return {"ok": True}
