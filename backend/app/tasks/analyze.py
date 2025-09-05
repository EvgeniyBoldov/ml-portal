from __future__ import annotations
from datetime import datetime
from celery import shared_task
from app.core.db import SessionLocal
from app.models.analyze import AnalysisDocuments
from .shared import log, RetryableError, task_metrics
from app.services.clients import llm_chat

@shared_task(name="app.tasks.analyze.run", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def run(self, job_id: str, *, pipeline: dict | None = None) -> dict:
    with task_metrics("analyze.run", "analyze"):
        session = SessionLocal()
        try:
            job = session.get(AnalysisDocuments, job_id)
            if not job:
                raise RetryableError("job_not_found")
            # Сбор сообщений для LLM
            system = {"role": "system", "content": "Ты — аналитик. Кратко резюмируй данные и выдай ключевые пункты."}
            user_msg = {"role": "user", "content": (pipeline or {}).get("prompt", "Проанализируй документ и верни краткое резюме.")}
            content = llm_chat([system, user_msg], temperature=float((pipeline or {}).get("temperature", 0.2)))
            job.status = "done"
            job.updated_at = datetime.utcnow()
            job.result = {"summary": content, "pipeline": pipeline or {}}
            session.commit()
            return {"job_id": str(job.id), "status": job.status}
        finally:
            session.close()
