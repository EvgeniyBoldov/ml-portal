"""
Template collection endpoints: upload, list, get, update metadata/schema.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.config import get_settings
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType
from app.services.collection.template_analysis_orchestrator import TemplateAnalysisOrchestrator
from app.services.collection.template_status_stream import (
    TemplateStatusSubscriber,
    build_template_status_graph,
)
from app.repositories.template_analysis_status_repo import AsyncTemplateAnalysisStatusRepository
from app.services.collection.template_upload_service import TemplateUploadService
from app.services.collection.row_service import CollectionRowService
from app.services.collection.status_snapshot_service import CollectionStatusSnapshotService
from app.services.collection.template_contract import TemplateContract, FieldSource
from app.core.sse import format_sse
import redis.asyncio as aioredis

logger = get_logger(__name__)
router = APIRouter()


class UpdateTemplateSchemaRequest(BaseModel):
    template_schema: dict


class UpdateTemplateRequest(BaseModel):
    description: str | None = None
    template_schema: dict | None = None
    status: str | None = None


class AnalyzeTemplatesRequest(BaseModel):
    row_ids: list[uuid.UUID]


def _resolve_next_template_status(existing: dict, updates: dict) -> str:
    current_status = str(existing.get("status") or "uploaded").strip().lower()
    explicit_status = str(updates.get("status") or "").strip().lower()
    allowed_statuses = {"uploaded", "analyzed", "ready", "archived"}
    if explicit_status:
        if explicit_status not in allowed_statuses:
            raise HTTPException(status_code=400, detail="Invalid template status")
        return explicit_status

    if current_status == "archived":
        return "archived"

    merged = dict(existing)
    merged.update(updates)
    has_description = bool(str(merged.get("description") or "").strip())
    has_schema = merged.get("template_schema") is not None
    if has_description and has_schema:
        return "ready"
    if has_description or has_schema:
        return "analyzed"
    return current_status or "uploaded"


async def _update_template_row(
    *,
    collection: Collection,
    row_id: uuid.UUID,
    payload: dict,
    session: AsyncSession,
) -> dict:
    row_service = CollectionRowService(session)
    existing = await row_service.get_row_by_id(collection, row_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template row not found")

    updates = dict(payload)
    skip_vectorization = set(payload.keys()) == {"status"}
    explicit_status = str(updates.pop("status", "") or "").strip().lower()
    if explicit_status:
        updates["status"] = explicit_status
    updates["status"] = _resolve_next_template_status(existing, updates)

    updated = await row_service.update_row(
        collection,
        row_id,
        updates,
        skip_vectorization=skip_vectorization,
    )
    await CollectionStatusSnapshotService(session).sync_collection_status(collection, persist=False)
    await session.commit()
    if not updated:
        raise HTTPException(status_code=404, detail="Template row not found")
    return updated


async def _get_template_row(
    collection: Collection,
    row_id: uuid.UUID,
    session: AsyncSession,
) -> dict:
    row_service = CollectionRowService(session)
    row = await row_service.get_row_by_id(collection, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template row not found")
    return row


async def _resolve_template_collection(
    collection_id: uuid.UUID,
    session: AsyncSession,
    user: UserCtx,
) -> Collection:
    from app.services.collection_service import CollectionService
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if str(collection.tenant_id) not in {str(t) for t in user.tenant_ids}:
        raise HTTPException(status_code=403, detail="Access denied")
    if collection.collection_type != CollectionType.TEMPLATE.value:
        raise HTTPException(status_code=400, detail="Collection is not a template collection")
    await service.ensure_contract_fields_present(collection, ensure_vector_infra=False)
    return collection


@router.post("/{collection_id}/templates/upload")
async def upload_template(
    collection_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    from app.services.collection_service import CollectionService
    service = CollectionService(session)
    # Persist one-time schema self-healing before row insert so DDL is not rolled back
    # together with a failed upload transaction on legacy template tables.
    await service.ensure_contract_fields_present(collection, ensure_vector_infra=True)
    await session.commit()
    file_content = await file.read()

    upload_service = TemplateUploadService(session)
    result = await upload_service.upload_template(
        collection=collection,
        file_content=file_content,
        filename=file.filename or f"template_{uuid.uuid4()}",
        content_type=file.content_type,
        user_id=user.id,
    )
    await CollectionStatusSnapshotService(session).sync_collection_status(collection, persist=False)
    await session.commit()
    task_ids = TemplateAnalysisOrchestrator.enqueue_all(
        collection_id=collection.id,
        row_id=result["row_id"],
        countdown=1,
    )
    result.update(task_ids)
    return result


@router.post("/{collection_id}/templates/analyze")
async def analyze_templates(
    collection_id: uuid.UUID,
    data: AnalyzeTemplatesRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    if not data.row_ids:
        raise HTTPException(status_code=400, detail="No template rows selected")

    row_service = CollectionRowService(session)
    results: list[dict[str, str]] = []
    missing: list[str] = []

    for row_id in data.row_ids:
        row = await row_service.get_row_by_id(collection, row_id)
        if not row:
            missing.append(str(row_id))
            continue

        task_ids = TemplateAnalysisOrchestrator.enqueue_all(
            collection_id=collection.id,
            row_id=row_id,
            countdown=1,
        )
        results.append(
            {
                "row_id": str(row_id),
                **task_ids,
            }
        )

    await CollectionStatusSnapshotService(session).sync_collection_status(collection, persist=False)
    await session.commit()

    if missing and not results:
        raise HTTPException(status_code=404, detail="No selected template rows were found")

    return {
        "collection_id": str(collection.id),
        "queued": len(results),
        "missing": missing,
        "items": results,
    }


@router.get("/{collection_id}/templates/{row_id}/status-graph")
async def get_template_status_graph(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    row = await _get_template_row(collection, row_id, session)
    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    nodes = await status_repo.get_nodes_by_row_id(row_id)
    return build_template_status_graph(
        row,
        collection_id=str(collection.id),
        analysis_nodes=[
            {
                "node_key": node.node_key,
                "status": node.status,
                "error_short": node.error_short,
                "metrics_json": node.metrics_json,
            }
            for node in nodes
        ],
    )


@router.get("/{collection_id}/templates/{row_id}/status/events")
async def stream_template_status(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    if user.role == "reader":
        raise HTTPException(status_code=403, detail="Access denied")

    collection = await _resolve_template_collection(collection_id, session, user)
    row = await _get_template_row(collection, row_id, session)
    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    nodes = await status_repo.get_nodes_by_row_id(row_id)
    await session.close()

    settings = get_settings()
    if not settings.REDIS_URL:
        raise HTTPException(status_code=503, detail="Redis is not available")

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    subscriber = TemplateStatusSubscriber(redis_client, row_id)
    row_id_str = str(row_id)
    async def event_generator():
        try:
            await subscriber.subscribe()
            yield format_sse(
                data={
                    "graph": build_template_status_graph(
                        row,
                        collection_id=str(collection.id),
                        analysis_nodes=[
                            {
                                "node_key": node.node_key,
                                "status": node.status,
                                "error_short": node.error_short,
                                "metrics_json": node.metrics_json,
                            }
                            for node in nodes
                        ],
                    ),
                    "collection_id": str(collection.id),
                    "row_id": row_id_str,
                },
                event="snapshot",
            )

            listener = subscriber.listen().__aiter__()
            while True:
                try:
                    event = await listener.__anext__()
                except StopAsyncIteration:
                    break

                event_type = event.get("event_type", "snapshot")
                if event_type != "snapshot":
                    continue
                graph = event.get("graph")
                if not graph:
                    continue
                yield format_sse(data=event, event="snapshot")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Template status stream error: %s", exc, exc_info=True)
            yield format_sse(data={"error": "Internal server error"}, event="error")
        finally:
            await subscriber.unsubscribe()
            try:
                await redis_client.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{collection_id}/templates")
async def list_templates(
    collection_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    row_service = CollectionRowService(session)
    offset = (page - 1) * size
    rows = await row_service.search(collection, limit=size, offset=offset)
    total = await row_service.count(collection)
    return {
        "items": rows,
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/{collection_id}/templates/{row_id}")
async def get_template(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    row_service = CollectionRowService(session)
    row = await row_service.get_row_by_id(collection, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template row not found")
    return row


@router.patch("/{collection_id}/templates/{row_id}")
async def update_template(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    data: UpdateTemplateRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No template fields to update")
    return await _update_template_row(
        collection=collection,
        row_id=row_id,
        payload=payload,
        session=session,
    )


@router.patch("/{collection_id}/templates/{row_id}/schema")
async def update_template_schema(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    data: UpdateTemplateSchemaRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    return await _update_template_row(
        collection=collection,
        row_id=row_id,
        payload={"template_schema": data.template_schema},
        session=session,
    )



@router.patch("/{collection_id}/templates/{row_id}/schema/admin")
async def update_template_schema_admin(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    data: UpdateTemplateSchemaRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    """
    Admin edit of template schema with provenance.
    Sets source=admin and locked=true for all edited fields.
    """
    collection = await _resolve_template_collection(collection_id, session, user)
    row_service = CollectionRowService(session)
    row = await row_service.get_row_by_id(collection, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template row not found")
    
    # Parse incoming schema and mark as admin/locked
    raw_schema = data.template_schema
    if "fields" in raw_schema:
        for field in raw_schema["fields"]:
            field["source"] = FieldSource.ADMIN.value
            field["locked"] = True
    
    # Merge with existing if present
    existing_raw = row.get("template_schema") or {}
    if existing_raw and "fields" in existing_raw:
        existing_contract = TemplateContract.from_jsonb(existing_raw)
        new_contract = TemplateContract.from_jsonb(raw_schema)
        merged = TemplateContract.merge_contract(existing_contract, new_contract)
        raw_schema = merged.to_jsonb()
    
    return await _update_template_row(
        collection=collection,
        row_id=row_id,
        payload={"template_schema": raw_schema},
        session=session,
    )
