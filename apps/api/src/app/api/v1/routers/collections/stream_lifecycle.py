"""
Collection document ingest lifecycle endpoints.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user, get_redis_client as redis_dependency
from app.core.security import UserCtx
from app.services.rag_event_publisher import RAGEventPublisher
from app.services.rag_ingest_service import RAGIngestService
from app.services.rag_status_manager import RAGStatusManager, StageStatus as _Stage

from .stream_shared import _problem, _ensure_worker_ready, _resolve_collection_and_doc

router = APIRouter()


@router.post("/{collection_id}/docs/{doc_id}/ingest/start")
async def start_collection_ingest(
    collection_id: uuid.UUID,
    doc_id: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    redis=Depends(redis_dependency),
):
    collection, document, doc_uuid, repo_factory = await _resolve_collection_and_doc(
        collection_id, doc_id, session, user
    )

    event_publisher = RAGEventPublisher(redis)
    status_manager = RAGStatusManager(session, repo_factory, event_publisher)

    await _ensure_worker_ready()

    start_lock = redis.lock(f"lock:ingest:start:{doc_uuid}", timeout=30, blocking_timeout=0) if redis else None
    lock_acquired = False
    if start_lock is not None:
        lock_acquired = bool(await start_lock.acquire(blocking=False))
        if not lock_acquired:
            return {
                "status": "success",
                "message": "Ingest already running",
                "document_id": doc_id,
                "embedding_models": [],
                "already_running": True,
                "active_stages": [],
            }

    try:
        ingest_policy = await status_manager.get_ingest_policy(doc_uuid)
        if not ingest_policy["start_allowed"]:
            reason = ingest_policy.get("start_reason")
            if reason == "ingest_already_running":
                return {
                    "status": "success",
                    "message": "Ingest already running",
                    "document_id": doc_id,
                    "embedding_models": [],
                    "already_running": True,
                    "active_stages": ingest_policy.get("active_stages", []),
                }
            if reason == "document_archived":
                raise _problem(409, "Document is archived", reason)
            raise _problem(409, "Ingest not allowed", reason)

        await status_manager.start_ingest(doc_uuid)
        await event_publisher.publish_ingest_started(doc_id=doc_uuid, tenant_id=document.tenant_id, user_id=user.id)
        embedding_models = await status_manager.dispatch_ingest_pipeline(doc_uuid, document.tenant_id)
        return {"status": "success", "message": "Ingest started", "document_id": doc_id, "embedding_models": embedding_models}
    finally:
        if start_lock is not None and lock_acquired:
            try:
                await start_lock.release()
            except Exception:
                pass


@router.post("/{collection_id}/docs/{doc_id}/ingest/stop")
async def stop_collection_ingest(
    collection_id: uuid.UUID,
    doc_id: str,
    stage: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    redis=Depends(redis_dependency),
):
    collection, document, doc_uuid, repo_factory = await _resolve_collection_and_doc(
        collection_id, doc_id, session, user
    )

    event_publisher = RAGEventPublisher(redis)
    status_manager = RAGStatusManager(session, repo_factory, event_publisher)

    ingest_policy = await status_manager.get_ingest_policy(doc_uuid)
    if stage == "pipeline":
        active_controls = [item for item in ingest_policy.get("controls", []) if item.get("can_stop")]
        pipeline_control = next((item for item in active_controls if item.get("node_type") == "pipeline"), None)
        selected = pipeline_control or (active_controls[0] if active_controls else None)
        if not selected:
            raise _problem(409, "Stage is not stoppable", "stage_not_stoppable", stage=stage)
        stage = selected["stage"]

    controls = {item["stage"]: item for item in ingest_policy.get("controls", [])}
    control = controls.get(stage)
    if not control:
        raise _problem(404, "Stage not found", "stage_not_found", stage=stage)
    if not control.get("can_stop"):
        raise _problem(409, "Stage is not stoppable", "stage_not_stoppable", stage=stage, status=control.get("status"))

    celery_task_id = await status_manager.stop_stage(doc_uuid, stage)
    if celery_task_id:
        from app.celery_app import app as celery_app

        try:
            celery_app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
        except Exception:
            pass

    return {"status": "success", "message": f"Stage {stage} stopped", "document_id": doc_id, "stage": stage}


@router.post("/{collection_id}/docs/{doc_id}/ingest/retry")
async def retry_collection_ingest(
    collection_id: uuid.UUID,
    doc_id: str,
    stage: str,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    redis=Depends(redis_dependency),
):
    collection, document, doc_uuid, repo_factory = await _resolve_collection_and_doc(
        collection_id, doc_id, session, user
    )

    await _ensure_worker_ready()

    event_publisher = RAGEventPublisher(redis)
    status_manager = RAGStatusManager(session, repo_factory, event_publisher)
    ingest_policy = await status_manager.get_ingest_policy(doc_uuid)
    controls = {item["stage"]: item for item in ingest_policy.get("controls", [])}
    control = controls.get(stage)
    if not control:
        raise _problem(404, "Stage not found", "stage_not_found", stage=stage)

    if not control.get("retry_supported"):
        raise _problem(409, "Retry is not supported for this stage", "retry_not_supported", stage=stage)

    current = _Stage(control["status"])
    if current in {_Stage.PROCESSING, _Stage.QUEUED}:
        raise _problem(409, "Stage is already running", "stage_already_running", stage=stage, status=current.value)

    if not control.get("can_retry"):
        raise _problem(409, "Stage is not retryable", "stage_not_retryable", stage=stage, status=current.value)

    await status_manager.retry_stage(doc_uuid, stage)
    await status_manager.dispatch_stage_retry(doc_uuid, document.tenant_id, stage)
    return {"status": "success", "message": "Stage restarted", "document_id": doc_id, "stage": stage}
