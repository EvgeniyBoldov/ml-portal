"""
Collections CSV upload endpoints.
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.logging import get_logger
from app.repositories.factory import get_async_repository_factory, AsyncRepositoryFactory
from app.services.collection_service import CollectionService
from app.services.collection_csv_service import CollectionCSVService, CSVValidationError

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


@router.post("/{slug}/preview")
async def preview_csv(
    slug: str,
    file: UploadFile = File(...),
    encoding: str = Query("utf-8"),
    delimiter: str = Query(","),
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
) -> CSVPreviewResponse:
    """
    Preview CSV file before upload.
    Returns column mapping and sample rows.
    """
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)
    collection = await service.get_by_slug(tenant_id, slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    try:
        content = await file.read()
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

    except CSVValidationError as e:
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
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
) -> CSVUploadResponse:
    """
    Upload CSV file to collection.
    
    Args:
        slug: Collection slug
        file: CSV file
        encoding: File encoding (default: utf-8)
        delimiter: CSV delimiter (default: ,)
        skip_errors: If true, skip invalid rows instead of failing
    """
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)
    collection = await service.get_by_slug(tenant_id, slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    try:
        content = await file.read()
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
            await session.commit()
        else:
            inserted = 0

        return CSVUploadResponse(
            inserted_rows=inserted,
            errors=errors[:20] if errors else [],
            total_rows=len(valid_rows) + len(errors),
        )

    except CSVValidationError as e:
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
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Get data from collection with pagination"""
    tenant_id = repo_factory.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")

    service = CollectionService(session)
    collection = await service.get_by_slug(tenant_id, slug)

    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")

    rows = await service.search(collection, filters={}, limit=limit, offset=offset)
    total = collection.row_count

    return {
        "items": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
