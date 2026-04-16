"""
RAG Status Stream - SSE endpoint для получения обновлений статусов
"""
from __future__ import annotations
from typing import Any, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_sse, db_session, db_uow
from app.core.security import UserCtx
from app.core.sse import format_sse
from app.services.rag_event_publisher import RAGEventSubscriber
from app.core.logging import get_logger
import asyncio

logger = get_logger(__name__)

router = APIRouter(tags=["rag-status"])

# Redis dependency уже определён в app.api.deps
# Импортируем его здесь для использования
from app.api.deps import get_redis_client as redis_dependency

def _rag_problem(status_code: int, error: str, reason: str, **extra: Any) -> HTTPException:
    detail = {
        "error": error,
        "reason": reason,
    }
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)

def _is_retry_supported(stage: str) -> bool:
    return stage == "extract" or stage.startswith("embed.") or stage.startswith("index.")

async def _ensure_worker_ready() -> None:
    from app.celery_app import app as celery_app

    loop = asyncio.get_event_loop()
    inspect_result = await loop.run_in_executor(
        None,
        lambda: celery_app.control.ping(timeout=2.0),
    )
    if not inspect_result:
        raise _rag_problem(
            status_code=503,
            error="RAG worker is not available",
            reason="worker_unavailable",
        )


@router.get("/events")
async def stream_rag_status(
    user: UserCtx = Depends(get_current_user_sse),
    redis = Depends(redis_dependency),
    document_id: str | None = None,
):
    """
    SSE endpoint для получения обновлений статусов RAG документов
    
    **Права доступа:**
    - reader: НЕ имеет доступа (403)
    - editor: получает события только своего тенанта
    - admin: получает все события
    
    **Формат событий:**
    ```json
    {
      "event_type": "status_update",
      "document_id": "uuid",
      "tenant_id": "uuid",
      "stage": "extract",
      "status": "processing",
      "error": null,
      "metrics": {},
      "timestamp": "2025-11-04T20:30:00Z"
    }
    ```
    
    **Типы событий:**
    - status_update: обновление статуса этапа
    - status_initialized: инициализация статусов нового документа
    - ingest_started: начало инжеста
    - document_archived: документ архивирован
    - document_unarchived: документ разархивирован
    """
    # Проверка прав доступа
    if user.role == 'reader':
        raise HTTPException(
            status_code=403,
            detail="Readers do not have access to RAG status updates"
        )
    
    if not redis:
        raise HTTPException(
            status_code=503,
            detail="Redis is not available"
        )
    
    # Определяем параметры подписки
    is_admin = user.role == 'admin'
    # Fix: use tenant_ids[0] instead of non-existent tenant_id attribute
    tenant_id = None if is_admin else (user.tenant_ids[0] if user.tenant_ids else None)
    
    async def event_generator() -> AsyncGenerator[str, None]:
        """Генератор SSE событий с heartbeat"""
        subscriber = RAGEventSubscriber(
            redis_client=redis,
            tenant_id=tenant_id,
            is_admin=is_admin
        )
        
        try:
            await subscriber.subscribe()
            logger.info(f"User {user.id} ({user.role}) subscribed to RAG status stream (tenant={tenant_id})")
            
            # Merge event stream with heartbeat
            last_heartbeat = asyncio.get_event_loop().time()
            heartbeat_interval = 30  # seconds
            
            async for event in subscriber.listen():
                # Optional per-document filter to reduce client work
                if document_id and event.get("document_id") != document_id:
                    continue
                # Send event
                yield format_sse(
                    data=event,
                    event=event.get('event_type', 'status_update')
                )
                
                # Check if we need to send heartbeat
                current_time = asyncio.get_event_loop().time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    yield ": ping\n\n"
                    last_heartbeat = current_time
            
        except asyncio.CancelledError:
            logger.info(f"User {user.id} disconnected from RAG status stream")
        except Exception as e:
            logger.error(f"Error in RAG status stream: {e}")
            yield format_sse(
                data={'error': 'Internal server error'},
                event='error'
            )
        finally:
            await subscriber.unsubscribe()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Для nginx
            "Access-Control-Allow-Credentials": "true",
        }
    )


@router.get("/{document_id}")
async def get_document_status(
    document_id: str,
    user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_session)
):
    """
    Получить текущий статус документа (snapshot)
    
    Args:
        document_id: ID документа
        
    Returns:
        Полный статус документа со всеми этапами
    """
    from uuid import UUID
    from app.services.rag_status_manager import RAGStatusManager
    from app.repositories.factory import get_async_repository_factory
    
    # Проверка прав доступа
    if user.role == 'reader':
        raise HTTPException(
            status_code=403,
            detail="Readers do not have access to RAG documents"
        )
    
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    
    # Получаем документ для проверки прав
    repo_factory = get_async_repository_factory(session, user)
    rag_repo = repo_factory.get_rag_documents_repository()
    
    document = await rag_repo.get_by_id(repo_factory.tenant_id, doc_uuid)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Проверка tenant_id для editor
    user_tenant_id = user.tenant_ids[0] if user.tenant_ids else None
    if user.role == 'editor' and str(document.tenant_id) != user_tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Получаем статус
    status_manager = RAGStatusManager(session, repo_factory)
    status = await status_manager.get_document_status(doc_uuid)
    
    return status


@router.post("/{document_id}/ingest/start")
async def start_ingest(
    document_id: str,
    user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
    redis = Depends(redis_dependency)
):
    """
    Запустить инжест документа
    
    Args:
        document_id: ID документа
        
    Returns:
        Статус операции
    """
    from uuid import UUID
    from app.services.rag_status_manager import RAGStatusManager
    from app.repositories.factory import get_async_repository_factory
    
    # Проверка прав доступа
    if user.role not in ['editor', 'admin']:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    
    # Получаем документ для проверки прав
    repo_factory = get_async_repository_factory(session, user)
    rag_repo = repo_factory.get_rag_documents_repository()
    
    document = await rag_repo.get_by_id(repo_factory.tenant_id, doc_uuid)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Проверка tenant_id для editor
    user_tenant_id = user.tenant_ids[0] if user.tenant_ids else None
    if user.role == 'editor' and str(document.tenant_id) != user_tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Запускаем инжест
    from app.services.rag_event_publisher import RAGEventPublisher
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
                "document_id": document_id,
                "embedding_models": [],
                "already_running": True,
                "active_stages": [],
            }

    try:
        # Guard: проверяем можно ли запустить инжест
        guard = await status_manager.check_ingest_allowed(doc_uuid)
        if not guard["allowed"]:
            reason = guard["reason"]
            logger.info(
                "rag_ingest_guard_rejected",
                extra={
                    "document_id": str(doc_uuid),
                    "tenant_id": str(document.tenant_id),
                    "user_id": str(user.id),
                    "reason": reason,
                    "active_stages": guard.get("active_stages", []),
                },
            )
            if reason == "ingest_already_running":
                return {
                    "status": "success",
                    "message": "Ingest already running",
                    "document_id": document_id,
                    "embedding_models": [],
                    "already_running": True,
                    "active_stages": guard.get("active_stages", []),
                }
            elif reason == "document_archived":
                raise _rag_problem(
                    status_code=409,
                    error="Document is archived",
                    reason=reason,
                )
            else:
                raise _rag_problem(
                    status_code=409,
                    error="Ingest not allowed",
                    reason=reason,
                )
        
        await status_manager.start_ingest(doc_uuid)
        
        # Публикуем событие
        await event_publisher.publish_ingest_started(
            doc_id=doc_uuid,
            tenant_id=document.tenant_id,
            user_id=user.id
        )
        
        # Запускаем Celery pipeline через единый диспетчер
        embedding_models = await status_manager.dispatch_ingest_pipeline(doc_uuid, document.tenant_id)
        
        return {
            'status': 'success',
            'message': 'Ingest started',
            'document_id': document_id,
            'embedding_models': embedding_models
        }
    finally:
        if start_lock is not None and lock_acquired:
            try:
                await start_lock.release()
            except Exception:
                pass


@router.post("/{document_id}/ingest/stop")
async def stop_ingest(
    document_id: str,
    stage: str,
    user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
    redis = Depends(redis_dependency)
):
    """
    Остановить выполнение этапа
    
    Args:
        document_id: ID документа
        stage: Название этапа (extract, chunk, embed.model_id)
        
    Returns:
        Статус операции
    """
    from uuid import UUID
    from app.services.rag_status_manager import RAGStatusManager
    from app.repositories.factory import get_async_repository_factory
    
    # Проверка прав доступа
    if user.role not in ['editor', 'admin']:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    
    # Получаем документ для проверки прав
    repo_factory = get_async_repository_factory(session, user)
    rag_repo = repo_factory.get_rag_documents_repository()
    
    document = await rag_repo.get_by_id(repo_factory.tenant_id, doc_uuid)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Проверка tenant_id для editor
    user_tenant_id = user.tenant_ids[0] if user.tenant_ids else None
    if user.role == 'editor' and str(document.tenant_id) != user_tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Останавливаем этап
    from app.services.rag_event_publisher import RAGEventPublisher
    event_publisher = RAGEventPublisher(redis)
    
    status_manager = RAGStatusManager(session, repo_factory, event_publisher)
    if stage == "pipeline":
        ingest_policy = await status_manager.get_ingest_policy(doc_uuid)
        active_controls = [item for item in ingest_policy.get("controls", []) if item.get("can_stop")]
        pipeline_control = next((item for item in active_controls if item.get("node_type") == "pipeline"), None)
        selected = pipeline_control or (active_controls[0] if active_controls else None)
        if not selected:
            raise _rag_problem(
                status_code=409,
                error="Stage is not stoppable",
                reason="stage_not_stoppable",
                stage=stage,
            )
        stage = selected["stage"]

    current_node = await status_manager.status_repo.get_node(
        doc_uuid,
        'embedding' if stage.startswith('embed.') else ('index' if stage.startswith('index.') else 'pipeline'),
        stage.replace('embed.', '', 1).replace('index.', '', 1) if (stage.startswith('embed.') or stage.startswith('index.')) else stage,
    )
    if not current_node:
        raise _rag_problem(
            status_code=404,
            error="Stage not found",
            reason="stage_not_found",
            stage=stage,
        )

    if current_node.status not in {"queued", "processing"}:
        raise _rag_problem(
            status_code=409,
            error="Stage is not stoppable",
            reason="stage_not_stoppable",
            stage=stage,
            status=current_node.status,
        )
    
    celery_task_id = await status_manager.stop_stage(doc_uuid, stage)
    
    # Убиваем Celery задачу, если известен task_id
    if celery_task_id:
        from app.celery_app import app as celery_app
        try:
            celery_app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
        except Exception as e:
            logger.warning(f"Failed to revoke celery task {celery_task_id}: {e}")
    
    return {
        'status': 'success',
        'message': f'Stage {stage} stopped',
        'document_id': document_id,
        'stage': stage
    }


@router.post("/{document_id}/ingest/retry")
async def retry_ingest(
    document_id: str,
    stage: str,
    user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
    redis = Depends(redis_dependency)
):
    """
    Перезапустить этап
    
    Args:
        document_id: ID документа
        stage: Название этапа (extract, chunk, embed.model_id)
        
    Returns:
        Статус операции
    """
    from uuid import UUID
    from app.services.rag_status_manager import RAGStatusManager
    from app.repositories.factory import get_async_repository_factory
    
    # Проверка прав доступа
    if user.role not in ['editor', 'admin']:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    
    # Получаем документ для проверки прав
    repo_factory = get_async_repository_factory(session, user)
    rag_repo = repo_factory.get_rag_documents_repository()
    
    document = await rag_repo.get_by_id(repo_factory.tenant_id, doc_uuid)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Проверка tenant_id для editor
    user_tenant_id = user.tenant_ids[0] if user.tenant_ids else None
    if user.role == 'editor' and str(document.tenant_id) != user_tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    await _ensure_worker_ready()

    if not _is_retry_supported(stage):
        raise _rag_problem(
            status_code=409,
            error="Retry is not supported for this stage",
            reason="retry_not_supported",
            stage=stage,
        )

    # Перезапускаем этап (толерантно к текущему статусу)
    from app.services.rag_event_publisher import RAGEventPublisher
    event_publisher = RAGEventPublisher(redis)
    status_manager = RAGStatusManager(session, repo_factory, event_publisher)

    if stage.startswith('embed.'):
        node_type = 'embedding'
        node_key = stage.replace('embed.', '', 1)
    elif stage.startswith('index.'):
        node_type = 'index'
        node_key = stage.replace('index.', '', 1)
    else:
        node_type = 'pipeline'
        node_key = stage

    current_node = await status_manager.status_repo.get_node(doc_uuid, node_type, node_key)
    if not current_node:
        raise _rag_problem(
            status_code=404,
            error="Stage not found",
            reason="stage_not_found",
            stage=stage,
        )

    from app.services.rag_status_manager import StageStatus as _Stage
    current = _Stage(current_node.status)

    if current in {_Stage.PROCESSING, _Stage.QUEUED}:
        raise _rag_problem(
            status_code=409,
            error="Stage is already running",
            reason="stage_already_running",
            stage=stage,
            status=current.value,
        )

    await status_manager.retry_stage(doc_uuid, stage)
    await status_manager.dispatch_stage_retry(doc_uuid, document.tenant_id, stage)

    return {
        'status': 'success',
        'message': 'Stage restarted',
        'document_id': document_id,
        'stage': stage
    }
