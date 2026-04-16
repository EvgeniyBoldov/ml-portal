"""
Collections table endpoints: CSV upload, row CRUD, vectorization, template.
"""
from __future__ import annotations

from typing import Optional, Any, Dict
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.exceptions import CSVValidationError, UploadValidationError
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.models.collection import CollectionType
from app.services.collection_csv_service import CollectionCSVService
from app.services.collection_vectorization_orchestrator import CollectionVectorizationOrchestrator
from app.services.upload_intake_policy import UploadIntakePolicy

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
