"""
RAG Status Stream - SSE endpoint для получения обновлений статусов
"""
from __future__ import annotations
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_sse, db_session
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


@router.get("/{document_id}/status")
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
    session: AsyncSession = Depends(db_session),
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
    await status_manager.start_ingest(doc_uuid)
    
    # Публикуем событие
    await event_publisher.publish_ingest_started(
        doc_id=doc_uuid,
        tenant_id=document.tenant_id,
        user_id=user.id
    )
    
    # Запустить Celery задачи (новый модульный pipeline)
    from app.workers.tasks_rag_ingest import (
        extract_document,
        normalize_document,
        chunk_document,
        embed_chunks_model,
        index_model,
    )
    from celery import chain, group

    # Получаем embedding models
    embedding_models = await status_manager._get_target_models(doc_uuid)
    if not embedding_models:
        from app.core.config import get_embedding_models
        embedding_models = get_embedding_models()

    # Создаём pipeline: extract → normalize → chunk → group(embed per model)
    extract_task = extract_document.s(str(doc_uuid), str(document.tenant_id))
    normalize_task = normalize_document.s(str(document.tenant_id))
    chunk_task = chunk_document.s(str(document.tenant_id))

    # Для каждой модели собираем цепочку: embed -> index
    embedding_index_chains = [
        chain(
            embed_chunks_model.s(str(document.tenant_id), model_alias),
            index_model.s(str(document.tenant_id))
        )
        for model_alias in embedding_models
    ]

    # Полный пайплайн: extract → normalize → chunk → group(embed→index per model)
    pipeline = chain(extract_task, normalize_task, chunk_task, group(embedding_index_chains))
    pipeline.apply_async()
    
    return {
        'status': 'success',
        'message': 'Ingest started',
        'document_id': document_id,
        'embedding_models': embedding_models
    }


@router.post("/{document_id}/ingest/stop")
async def stop_ingest(
    document_id: str,
    stage: str,
    user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
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
    session: AsyncSession = Depends(db_session),
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
    
    # Перезапускаем этап (толерантно к текущему статусу)
    from app.services.rag_event_publisher import RAGEventPublisher
    event_publisher = RAGEventPublisher(redis)
    status_manager = RAGStatusManager(session, repo_factory, event_publisher)

    # Узнаём текущий статус узла
    node_type = 'embedding' if stage.startswith('embed.') else 'pipeline'
    node_key = stage.replace('embed.', '') if stage.startswith('embed.') else stage
    current_node = await status_manager.status_repo.get_node(doc_uuid, node_type, node_key)
    current = None
    if current_node:
        from app.services.rag_status_manager import StageStatus as _Stage
        current = _Stage(current_node.status)

    # Переходим в queued только если это уместно
    # - если failed/cancelled/completed → queued
    # - если pending → queued
    # - если уже queued → пропускаем смену статуса
    # - если processing → не трогаем статус
    from app.services.rag_status_manager import StageStatus as StageStatusEnum
    should_queue = False
    if current is None:
        should_queue = True
    elif current in {StageStatusEnum.FAILED, StageStatusEnum.CANCELLED, StageStatusEnum.COMPLETED, StageStatusEnum.PENDING}:
        should_queue = True

    if should_queue:
        try:
            await status_manager.transition_stage(doc_uuid, stage, StageStatusEnum.QUEUED)
        except Exception:
            # Игнорируем ошибки идемпотентности (например, QUEUED->QUEUED)
            pass

    # Запускаем соответствующие Celery задачи
    if stage == 'extract':
        from app.workers.tasks_rag_ingest import (
            extract_document,
            normalize_document,
            chunk_document,
            embed_chunks_model,
            index_model,
        )
        from celery import chain, group

        embedding_models = await status_manager._get_target_models(doc_uuid)
        if not embedding_models:
            from app.core.config import get_embedding_models
            embedding_models = get_embedding_models()

        extract_task = extract_document.s(str(doc_uuid), str(document.tenant_id))
        normalize_task = normalize_document.s(str(document.tenant_id))
        chunk_task = chunk_document.s(str(document.tenant_id))
        model_task_chains = [
            chain(
                embed_chunks_model.s(str(document.tenant_id), model_alias),
                index_model.s(str(document.tenant_id))
            )
            for model_alias in embedding_models
        ]
        pipeline = chain(
            extract_task,
            normalize_task,
            chunk_task,
            group(model_task_chains)
        )
        pipeline.apply_async()

    elif stage.startswith('embed.'):
        model_alias = stage.split('.', 1)[1]
        from app.workers.tasks_rag_ingest import embed_chunks_model
        # Допускаем прямой перезапуск embed: задача сама подтянет чанки из БД
        embed_chunks_model.delay({"source_id": str(doc_uuid)}, str(document.tenant_id), model_alias)
    else:
        # Для остальных стадий пока требуем полный рестарт или реализацию спец-логики
        logger.info(f"Retry for stage '{stage}' is not directly supported, use start_ingest or extract retry")

    return {
        'status': 'success',
        'message': 'Stage restarted',
        'document_id': document_id,
        'stage': stage
    }
