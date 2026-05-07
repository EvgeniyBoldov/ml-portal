"""
Collections table endpoints: CSV upload, row CRUD, vectorization, template.
"""
from __future__ import annotations

from typing import Optional, Any, Dict
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.exceptions import CSVValidationError, UploadValidationError
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.models.collection import CollectionType
from app.core.cache import get_cache
from app.services.file_delivery_service import FileDeliveryService
from app.services.collection_csv_service import CollectionCSVService
from app.services.collection_vectorization_orchestrator import CollectionVectorizationOrchestrator
from app.services.upload_intake_policy import UploadIntakePolicy
from app.workers.tasks_collection_export import (
    EXPORT_META_PREFIX,
    EXPORT_TTL_SECONDS,
    export_collection_csv,
)

from .upload_shared import _resolve_table_collection_by_slug

logger = get_logger(__name__)

router = APIRouter()


class CSVPreviewResponse(BaseModel):
    columns: list[str]
    matched_columns: list[str]
    unmatched_columns: list[str]
    missing_required: list[str]
    sample_rows: list[dict]
    total_rows: int
    can_upload: bool


class CSVUploadResponse(BaseModel):
    inserted_rows: int
    errors: list[dict]
    total_rows: int


class RowMutationRequest(BaseModel):
    data: Dict[str, Any]


class VectorizationResponse(BaseModel):
    status: str
    task_id: Optional[str] = None


class DocumentUploadPolicyResponse(BaseModel):
    max_bytes: int
    allowed_extensions: list[str]
    allowed_content_types_by_extension: dict[str, list[str]]


class CollectionExportStartResponse(BaseModel):
    export_id: str
    status: str
    task_id: str
    expires_in: int


class CollectionExportStatusResponse(BaseModel):
    export_id: str
    status: str
    file_id: Optional[str] = None
    download_url: Optional[str] = None
    file_name: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None


@router.get("/uploads/document-policy", response_model=DocumentUploadPolicyResponse)
async def get_document_upload_policy(
    _: UserCtx = Depends(get_current_user),
) -> DocumentUploadPolicyResponse:
    from app.core.config import get_settings

    settings = get_settings()
    allowed_extensions = UploadIntakePolicy.document_allowed_extensions()
    return DocumentUploadPolicyResponse(
        max_bytes=settings.UPLOAD_MAX_BYTES,
        allowed_extensions=allowed_extensions,
        allowed_content_types_by_extension=UploadIntakePolicy.document_allowed_content_types_by_extension(
            allowed_extensions
        ),
    )


@router.post("/{slug}/preview")
async def preview_csv(
    slug: str,
    file: UploadFile = File(...),
    encoding: str = Query("utf-8"),
    delimiter: str = Query(","),
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
) -> CSVPreviewResponse:
    collection, _, _ = await _resolve_table_collection_by_slug(slug, session, user, tenant_id)

    try:
        content = await file.read()
        UploadIntakePolicy.validate_csv_upload(
            filename=file.filename or f"{slug}.csv",
            content_type=file.content_type,
            size_bytes=len(content),
        )
        csv_service = CollectionCSVService(collection)
        preview = csv_service.preview_csv(
            content=content,
            encoding=encoding,
            delimiter=delimiter,
        )

        can_upload = len(preview["missing_required"]) == 0

        return CSVPreviewResponse(
            columns=preview["columns"],
            matched_columns=preview["matched_columns"],
            unmatched_columns=preview["unmatched_columns"],
            missing_required=preview["missing_required"],
            sample_rows=preview["sample_rows"],
            total_rows=preview["total_rows"],
            can_upload=can_upload,
        )
    except (CSVValidationError, UploadValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"CSV preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to preview CSV: {str(e)}")


@router.post("/{slug}/upload")
async def upload_csv(
    slug: str,
    file: UploadFile = File(...),
    encoding: str = Query("utf-8"),
    delimiter: str = Query(","),
    skip_errors: bool = Query(False),
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
) -> CSVUploadResponse:
    collection, service, resolved_tenant_id = await _resolve_table_collection_by_slug(
        slug, session, user, tenant_id
    )

    try:
        content = await file.read()
        UploadIntakePolicy.validate_csv_upload(
            filename=file.filename or f"{slug}.csv",
            content_type=file.content_type,
            size_bytes=len(content),
        )
        csv_service = CollectionCSVService(collection)

        valid_rows, errors = csv_service.parse_csv(
            content=content,
            encoding=encoding,
            delimiter=delimiter,
        )

        if errors and not skip_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"CSV validation failed with {len(errors)} errors",
                    "errors": errors[:20],
                }
            )

        if valid_rows:
            inserted = await service.insert_rows(collection, valid_rows)
            orchestrator = CollectionVectorizationOrchestrator(session)
            await session.commit()
            task_id = None
            if inserted > 0:
                task_id = await orchestrator.enqueue_for_collection(
                    collection=collection,
                    tenant_id=resolved_tenant_id,
                    reason="csv_upload",
                    countdown=3,
                )
                await session.commit()
        else:
            inserted = 0
            task_id = None

        response = CSVUploadResponse(
            inserted_rows=inserted,
            errors=errors[:20] if errors else [],
            total_rows=len(valid_rows) + len(errors),
        )
        return response
    except (CSVValidationError, UploadValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CSV upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload CSV: {str(e)}")


@router.get("/{slug}/data")
async def get_collection_data(
    slug: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, service, _ = await _resolve_table_collection_by_slug(slug, session, user, tenant_id)
    rows = await service.search(collection, filters={}, limit=limit, offset=offset, query=search)
    total = await service.count(collection, filters={}, query=search)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("/{slug}/rows")
async def create_collection_row(
    slug: str,
    request: RowMutationRequest,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, service, resolved_tenant_id = await _resolve_table_collection_by_slug(
        slug, session, user, tenant_id
    )
    row = await service.create_row(collection, request.data)
    await session.commit()
    orchestrator = CollectionVectorizationOrchestrator(session)
    task_id = await orchestrator.enqueue_for_collection(
        collection=collection,
        tenant_id=resolved_tenant_id,
        row_ids=[str(row["id"])],
        reason="row_create",
        countdown=3,
    )
    if task_id:
        await session.commit()
    return {"item": row, "vectorization_task_id": task_id}


@router.get("/{slug}/rows/{row_id}")
async def get_collection_row(
    slug: str,
    row_id: uuid.UUID,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, service, _ = await _resolve_table_collection_by_slug(slug, session, user, tenant_id)
    row = await service.get_row_by_id(collection, row_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")
    return {"item": row}


@router.patch("/{slug}/rows/{row_id}")
async def update_collection_row(
    slug: str,
    row_id: uuid.UUID,
    request: RowMutationRequest,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, service, resolved_tenant_id = await _resolve_table_collection_by_slug(
        slug, session, user, tenant_id
    )
    row = await service.update_row(collection, row_id, request.data)
    if not row:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")

    await session.commit()
    orchestrator = CollectionVectorizationOrchestrator(session)
    task_id = await orchestrator.enqueue_for_collection(
        collection=collection,
        tenant_id=resolved_tenant_id,
        row_ids=[str(row_id)],
        reason="row_update",
        countdown=3,
    )
    if task_id:
        await session.commit()
    return {"item": row, "vectorization_task_id": task_id}


@router.delete("/{slug}/data")
async def delete_collection_rows(
    slug: str,
    ids: list[uuid.UUID] = Query(...),
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, service, _ = await _resolve_table_collection_by_slug(slug, session, user, tenant_id)
    deleted = await service.delete_rows(collection, ids)
    await session.commit()
    return {"deleted": deleted, "ids": ids}


@router.get("/{slug}/template")
async def download_template(
    slug: str,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, _, _ = await _resolve_table_collection_by_slug(slug, session, user, tenant_id)
    headers = [f["name"] for f in collection.fields]
    csv_content = (",".join(headers) + "\n").encode("utf-8")
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={slug}_template.csv"},
    )


@router.post("/{slug}/export", response_model=CollectionExportStartResponse)
async def start_csv_export(
    slug: str,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, _, resolved_tenant_id = await _resolve_table_collection_by_slug(slug, session, user, tenant_id)
    if collection.collection_type != CollectionType.TABLE.value:
        raise HTTPException(status_code=400, detail="CSV export supported only for table collections")

    field_names = [str(f.get("name")) for f in (collection.fields or []) if str(f.get("name") or "").strip()]
    if not field_names:
        raise HTTPException(status_code=400, detail="Collection has no exportable fields")

    export_id = str(uuid.uuid4())
    cache = await get_cache()
    meta_key = f"{EXPORT_META_PREFIX}{export_id}"
    now = datetime.now(timezone.utc)
    await cache.set(
        meta_key,
        {
            "status": "pending",
            "tenant_id": str(resolved_tenant_id),
            "owner_id": str(user.id),
            "collection_id": str(collection.id),
            "collection_slug": collection.slug,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        ttl=EXPORT_TTL_SECONDS,
    )

    async_result = export_collection_csv.delay(
        export_id=export_id,
        tenant_id=str(resolved_tenant_id),
        owner_id=str(user.id),
        collection_id=str(collection.id),
        collection_slug=str(collection.slug),
        table_name=str(collection.table_name),
        field_names=field_names,
    )
    return CollectionExportStartResponse(
        export_id=export_id,
        status="pending",
        task_id=str(async_result.id),
        expires_in=EXPORT_TTL_SECONDS,
    )


@router.get("/{slug}/export/{export_id}", response_model=CollectionExportStatusResponse)
async def get_csv_export_status(
    slug: str,
    export_id: str,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    collection, _, resolved_tenant_id = await _resolve_table_collection_by_slug(slug, session, user, tenant_id)
    cache = await get_cache()
    meta = await cache.get(f"{EXPORT_META_PREFIX}{export_id}")
    if not meta:
        raise HTTPException(status_code=404, detail="Export not found or expired")
    if str(meta.get("tenant_id") or "") != str(resolved_tenant_id):
        raise HTTPException(status_code=404, detail="Export not found")
    if str(meta.get("owner_id") or "") != str(user.id):
        raise HTTPException(status_code=403, detail="Export access denied")
    if str(meta.get("collection_id") or "") != str(collection.id):
        raise HTTPException(status_code=404, detail="Export not found")

    status = str(meta.get("status") or "pending")
    if status != "ready":
        return CollectionExportStatusResponse(
            export_id=export_id,
            status=status,
            error=str(meta.get("error")) if meta.get("error") else None,
        )

    file_id = FileDeliveryService.make_collection_export_file_id(export_id)
    return CollectionExportStatusResponse(
        export_id=export_id,
        status="ready",
        file_id=file_id,
        download_url=f"/api/v1/files/{file_id}/download",
        file_name=str(meta.get("file_name") or f"{collection.slug}_export.csv"),
        content_type=str(meta.get("content_type") or "text/csv"),
        size_bytes=int(meta.get("size_bytes") or 0),
        expires_at=str(meta.get("expires_at") or ""),
    )


@router.post("/{slug}/revectorize")
async def revectorize_collection(
    slug: str,
    tenant_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
) -> VectorizationResponse:
    collection, _, resolved_tenant_id = await _resolve_table_collection_by_slug(
        slug, session, user, tenant_id
    )
    orchestrator = CollectionVectorizationOrchestrator(session)
    await orchestrator.prepare_full_revectorization(collection)
    await session.commit()
    task_id = await orchestrator.enqueue_for_collection(
        collection=collection,
        tenant_id=resolved_tenant_id,
        reason="manual_revectorize",
        countdown=1,
    )
    if task_id:
        await session.commit()
    return VectorizationResponse(status="queued", task_id=task_id)
