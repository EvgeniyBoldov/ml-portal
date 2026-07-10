"""
Template collection endpoints: upload, list, get, update metadata/schema.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.config import get_settings
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.models.collection import Collection, CollectionType
from app.services.collection.template_analysis_orchestrator import TemplateAnalysisOrchestrator
from app.services.collection.template_status_stream import (
    TemplateCollectionStatusSubscriber,
    TemplateStatusSubscriber,
    build_template_row_runtime_payload,
    build_template_status_graph,
)
from app.repositories.template_analysis_status_repo import AsyncTemplateAnalysisStatusRepository
from app.services.collection.template_upload_service import TemplateUploadService
from app.services.collection.row_service import CollectionRowService
from app.services.collection.status_snapshot_service import CollectionStatusSnapshotService
from app.services.collection.template_contract import TemplateContract, FieldSource
from app.services.collection_vectorization_orchestrator import CollectionVectorizationOrchestrator
from app.core.sse import format_sse
import redis.asyncio as aioredis

logger = get_logger(__name__)
router = APIRouter()


def _serialize_template_nodes(nodes: list) -> list[dict]:
    return [
        {
            "node_key": node.node_key,
            "status": node.status,
            "error_short": node.error_short,
            "metrics_json": node.metrics_json,
            "started_at": getattr(node, "started_at", None).isoformat() if getattr(node, "started_at", None) else None,
            "finished_at": getattr(node, "finished_at", None).isoformat() if getattr(node, "finished_at", None) else None,
        }
        for node in nodes
    ]


def _is_legacy_xls(file_meta: object) -> bool:
    if not isinstance(file_meta, dict):
        return False
    filename = str(file_meta.get("filename") or "").strip().lower()
    return filename.endswith(".xls")


def _mark_schema_fields_admin(fields: list[dict]) -> None:
    for field in fields:
        if not isinstance(field, dict):
            continue
        field["source"] = FieldSource.ADMIN.value
        field["locked"] = True
        nested = field.get("fields")
        if isinstance(nested, list):
            _mark_schema_fields_admin(nested)


class UpdateTemplateSchemaRequest(BaseModel):
    template_schema: dict


class UpdateTemplateRequest(BaseModel):
    description: str | None = None
    template_schema: dict | None = None
    status: str | None = None


class AnalyzeTemplatesRequest(BaseModel):
    row_ids: list[uuid.UUID]


class ApproveTemplateRequest(BaseModel):
    approved_by: str | None = None


def _resolve_next_template_status(existing: dict, updates: dict) -> str:
    current_status = str(existing.get("status") or "uploaded").strip().lower()
    explicit_status = str(updates.get("status") or "").strip().lower()
    allowed_statuses = {"uploaded", "analyzed", "archived"}
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


async def _load_template_runtime_rows(
    *,
    collection: Collection,
    session: AsyncSession,
    rows: list[dict],
) -> list[dict]:
    if not rows:
        return []
    row_ids = [str(row["id"]) for row in rows if row.get("id")]
    if not row_ids:
        return []
    placeholders = ", ".join(f":rid_{idx}" for idx in range(len(row_ids)))
    params = {f"rid_{idx}": row_id for idx, row_id in enumerate(row_ids)}
    vector_meta_result = await session.execute(
        text(
            f"SELECT id::text AS id, _vector_status, _vector_error, _vector_chunk_count "
            f"FROM {collection.table_name} WHERE id::text IN ({placeholders})"
        ),
        params,
    )
    vector_meta = {
        str(item["id"]): dict(item)
        for item in vector_meta_result.mappings().all()
    }

    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    payloads: list[dict] = []
    for row in rows:
        row_id = uuid.UUID(str(row["id"]))
        nodes = await status_repo.get_nodes_by_row_id(row_id)
        payloads.append(
            build_template_row_runtime_payload(
                {
                    **row,
                    **vector_meta.get(str(row["id"]), {}),
                    "has_vector_search": bool(collection.has_vector_search),
                },
                collection_id=str(collection.id),
                analysis_nodes=_serialize_template_nodes(nodes),
            )
        )
    return payloads


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
    logger.info(
        "template_upload_received",
        extra={
            "collection_id": str(collection.id),
            "row_id": result["row_id"],
            "upload_filename": file.filename,
            "content_type": file.content_type,
            "file_size": len(file_content),
        },
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
    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    results: list[dict[str, str]] = []
    missing: list[str] = []

    for row_id in data.row_ids:
        row = await row_service.get_row_by_id(collection, row_id)
        if not row:
            missing.append(str(row_id))
            continue
        if _is_legacy_xls(row.get("file")):
            raise HTTPException(
                status_code=400,
                detail=f"Template row {row_id} uses legacy .xls and must be re-uploaded as .xlsx or .xlsm",
            )

        await status_repo.delete_nodes_by_row_id(collection.id, row_id)
        await row_service.update_row(collection, row_id, {"status": "uploaded"}, skip_vectorization=True)

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


@router.post("/{collection_id}/templates/{row_id}/approve")
async def approve_template(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    data: ApproveTemplateRequest | None = None,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    row_service = CollectionRowService(session)
    row = await row_service.get_row_by_id(collection, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template row not found")

    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    nodes = await status_repo.get_nodes_by_row_id(row_id)
    graph = build_template_status_graph(
        {
            **row,
            "has_vector_search": bool(collection.has_vector_search),
        },
        collection_id=str(collection.id),
        analysis_nodes=_serialize_template_nodes(nodes),
    )
    if not bool(graph.get("approval_required")):
        raise HTTPException(status_code=400, detail="Template is not awaiting approval")

    approved_at = datetime.now(timezone.utc)
    approver = data.approved_by if data and data.approved_by else str(user.id)
    await status_repo.upsert_node(
        collection_id=collection.id,
        row_id=row_id,
        node_key="approval",
        status="completed",
        metrics_json={
            "approval_state": "approved",
            "approved_by": approver,
            "approved_at": approved_at.isoformat(),
            "description_edited": False,
            "schema_edited": False,
        },
        finished_at=approved_at,
    )
    logger.info(
        "template_approval_completed",
        extra={
            "collection_id": str(collection.id),
            "row_id": str(row_id),
            "approved_by": approver,
            "approved_at": approved_at.isoformat(),
        },
    )

    next_status = "ready" if not collection.has_vector_search else "analyzed"
    await row_service.update_row(collection, row_id, {"status": next_status}, skip_vectorization=not collection.has_vector_search)
    await CollectionStatusSnapshotService(session).sync_collection_status(collection, persist=False)
    await session.commit()

    vectorization_task_id = None
    if collection.has_vector_search:
        vectorization_task_id = CollectionVectorizationOrchestrator.enqueue(
            collection_id=collection.id,
            tenant_id=collection.tenant_id,
            row_ids=[str(row_id)],
            countdown=1,
        )

    refreshed_row = await row_service.get_row_by_id(collection, row_id)
    runtime_rows = await _load_template_runtime_rows(collection=collection, session=session, rows=[refreshed_row or row])
    return {
        "item": runtime_rows[0] if runtime_rows else (refreshed_row or row),
        "vectorization_task_id": vectorization_task_id,
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
    runtime_rows = await _load_template_runtime_rows(collection=collection, session=session, rows=[row])
    row_payload = runtime_rows[0] if runtime_rows else {**row, "has_vector_search": bool(collection.has_vector_search)}
    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    nodes = await status_repo.get_nodes_by_row_id(row_id)
    return build_template_status_graph(
        row_payload,
        collection_id=str(collection.id),
        analysis_nodes=_serialize_template_nodes(nodes),
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
    runtime_rows = await _load_template_runtime_rows(collection=collection, session=session, rows=[row])
    row_payload = runtime_rows[0] if runtime_rows else {**row, "has_vector_search": bool(collection.has_vector_search)}
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
                        row_payload,
                        collection_id=str(collection.id),
                        analysis_nodes=_serialize_template_nodes(nodes),
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


@router.get("/{collection_id}/templates/status/events")
async def stream_template_collection_status(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    if user.role == "reader":
        raise HTTPException(status_code=403, detail="Access denied")

    collection = await _resolve_template_collection(collection_id, session, user)
    initial_rows = await _load_template_runtime_rows(
        collection=collection,
        session=session,
        rows=await CollectionRowService(session).search(collection, limit=500, offset=0),
    )
    await session.close()

    settings = get_settings()
    if not settings.REDIS_URL:
        raise HTTPException(status_code=503, detail="Redis is not available")

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    subscriber = TemplateCollectionStatusSubscriber(redis_client, collection_id)

    async def event_generator():
        try:
            await subscriber.subscribe()
            yield format_sse(
                data={"items": initial_rows, "collection_id": str(collection.id)},
                event="snapshot",
            )

            listener = subscriber.listen().__aiter__()
            while True:
                try:
                    event = await listener.__anext__()
                except StopAsyncIteration:
                    break
                yield format_sse(data=event, event=event.get("event_type", "snapshot"))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Template collection status stream error: %s", exc, exc_info=True)
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
    rows = await _load_template_runtime_rows(collection=collection, session=session, rows=rows)
    return {
        "items": rows,
        "total": total,
        "page": page,
        "size": size,
    }


@router.delete("/{collection_id}/templates")
async def delete_templates(
    collection_id: uuid.UUID,
    ids: list[uuid.UUID] = Query(...),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    if not ids:
        raise HTTPException(status_code=400, detail="No template rows selected")

    row_service = CollectionRowService(session)
    deleted = await row_service.delete_rows(collection, ids)
    await CollectionStatusSnapshotService(session).sync_collection_status(collection, persist=False)
    await session.commit()
    return {"deleted": deleted, "ids": [str(row_id) for row_id in ids]}


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
    runtime_rows = await _load_template_runtime_rows(collection=collection, session=session, rows=[row])
    return runtime_rows[0] if runtime_rows else row


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
    result = await _update_template_row(
        collection=collection,
        row_id=row_id,
        payload=payload,
        session=session,
    )
    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    description_changed = "description" in payload
    schema_changed = "template_schema" in payload
    if description_changed or schema_changed:
        edited_by = str(user.id)
        approval_node = await status_repo.get_node(row_id, "approval")
        approval_record = await status_repo.upsert_node(
            collection_id=collection.id,
            row_id=row_id,
            node_key="approval",
            status="pending",
            metrics_json={
                **((approval_node.metrics_json or {}) if approval_node and isinstance(approval_node.metrics_json, dict) else {}),
                "edited_by": edited_by,
                "description_edited": description_changed,
                "schema_edited": schema_changed,
            },
            finished_at=None,
        )
        approval_record.finished_at = None
        await session.commit()
    runtime_rows = await _load_template_runtime_rows(collection=collection, session=session, rows=[result])
    return runtime_rows[0] if runtime_rows else result


@router.patch("/{collection_id}/templates/{row_id}/schema")
async def update_template_schema(
    collection_id: uuid.UUID,
    row_id: uuid.UUID,
    data: UpdateTemplateSchemaRequest,
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection = await _resolve_template_collection(collection_id, session, user)
    result = await _update_template_row(
        collection=collection,
        row_id=row_id,
        payload={"template_schema": data.template_schema},
        session=session,
    )
    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    approval_node = await status_repo.get_node(row_id, "approval")
    approval_record = await status_repo.upsert_node(
        collection_id=collection.id,
        row_id=row_id,
        node_key="approval",
        status="pending",
        metrics_json={
            **((approval_node.metrics_json or {}) if approval_node and isinstance(approval_node.metrics_json, dict) else {}),
            "edited_by": str(user.id),
            "schema_edited": True,
        },
        finished_at=None,
    )
    approval_record.finished_at = None
    await session.commit()
    runtime_rows = await _load_template_runtime_rows(collection=collection, session=session, rows=[result])
    return runtime_rows[0] if runtime_rows else result



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
    
    # Mark submitted fields as admin/locked (provenance)
    raw_schema = data.template_schema
    if isinstance(raw_schema.get("fields"), list):
        _mark_schema_fields_admin(raw_schema["fields"])

    # Validate structure strictly — never silently wipe the schema
    try:
        new_contract = TemplateContract.model_validate(raw_schema)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid template schema: {exc}")

    # Admin-priority merge: admin fields win; preserve existing fields the
    # admin did not submit (matched by key). merge_contract is NOT used here
    # because its semantics keep *existing* protected fields, which would
    # discard the admin's new edits.
    existing_contract = TemplateContract.from_jsonb(row.get("template_schema") or {})
    submitted_keys = {f.key for f in new_contract.fields}
    preserved = [f for f in existing_contract.fields if f.key not in submitted_keys]
    merged_node_meta = {
        **{key: value for key, value in existing_contract.node_meta.items() if key not in submitted_keys},
        **new_contract.node_meta,
    }
    final_contract = TemplateContract(
        contract_version=new_contract.contract_version,
        format=new_contract.format or existing_contract.format,
        fields=new_contract.fields + preserved,
        node_meta=merged_node_meta,
    )

    result = await _update_template_row(
        collection=collection,
        row_id=row_id,
        payload={"template_schema": final_contract.to_jsonb()},
        session=session,
    )
    status_repo = AsyncTemplateAnalysisStatusRepository(session)
    approval_node = await status_repo.get_node(row_id, "approval")
    approval_record = await status_repo.upsert_node(
        collection_id=collection.id,
        row_id=row_id,
        node_key="approval",
        status="pending",
        metrics_json={
            **((approval_node.metrics_json or {}) if approval_node and isinstance(approval_node.metrics_json, dict) else {}),
            "edited_by": str(user.id),
            "schema_edited": True,
        },
        finished_at=None,
    )
    approval_record.finished_at = None
    await session.commit()
    runtime_rows = await _load_template_runtime_rows(collection=collection, session=session, rows=[result])
    return runtime_rows[0] if runtime_rows else result
