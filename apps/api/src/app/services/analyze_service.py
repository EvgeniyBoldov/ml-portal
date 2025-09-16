from __future__ import annotations
from sqlalchemy.orm import Session
from app.repositories.analyze_repo import AnalyzeRepo

def create_job(session: Session, uploaded_by=None, url_file: str | None = None):
    return AnalyzeRepo(session).create_document(uploaded_by=uploaded_by, url_file=url_file, status="queued")

def list_jobs(session: Session, limit: int = 50):
    return AnalyzeRepo(session).list(limit=limit)

def get_job(session: Session, job_id):
    return AnalyzeRepo(session).get(job_id)

def delete_job(session: Session, job_id):
    repo = AnalyzeRepo(session)
    doc = repo.get(job_id)
    if not doc:
        return False
    repo.delete(doc)
    return True
