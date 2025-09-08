from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.api.deps import db_session, get_current_user
from app.services.analyze_service import create_job, list_jobs, get_job, delete_job
from app.tasks.analyze import run as analyze_run

router = APIRouter(prefix="/analyze", tags=["analyze"])

@router.get("")
def list_(session: Session = Depends(db_session), user=Depends(get_current_user)):
	rows = list_jobs(session)
	return [{
		"id": str(r.id),
		"status": getattr(r, "status", None),
		"date_upload": getattr(r, "date_upload", None),
		"error": getattr(r, "error", None),
	} for r in rows]

@router.post("", status_code=202)
def create(
	payload: dict | None = None,
	file: UploadFile | None = File(None),
	url: str | None = Form(None),
	session: Session = Depends(db_session),
	user=Depends(get_current_user)
):
	if file is not None:
		job = create_job(session, uploaded_by=user["id"], url_file=file.filename)
		analyze_run.delay(str(job.id), pipeline=None)
		return {"id": str(job.id), "status": getattr(job, "status", "queued"), "accepted": True}
	if payload and payload.get("url"):
		job = create_job(session, uploaded_by=user["id"], url_file=payload.get("url"))
		analyze_run.delay(str(job.id), pipeline=None)
		return {"id": str(job.id), "status": getattr(job, "status", "queued"), "accepted": True}
	if url:
		job = create_job(session, uploaded_by=user["id"], url_file=url)
		analyze_run.delay(str(job.id), pipeline=None)
		return {"id": str(job.id), "status": getattr(job, "status", "queued"), "accepted": True}
	raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_file_or_url")

@router.get("/{job_id}")
def get(job_id: str, session: Session = Depends(db_session), user=Depends(get_current_user)):
	job = get_job(session, job_id)
	if not job:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
	return {
		"id": str(job.id),
		"status": getattr(job, "status", None),
		"result": getattr(job, "result", None),
		"error": getattr(job, "error", None),
	}

@router.delete("/{job_id}")
def delete(job_id: str, session: Session = Depends(db_session), user=Depends(get_current_user)):
	ok = delete_job(session, job_id)
	if not ok:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
	return {"ok": True}
