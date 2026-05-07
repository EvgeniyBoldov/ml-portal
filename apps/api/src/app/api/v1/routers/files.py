from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.repositories.factory import AsyncRepositoryFactory, get_async_repository_factory
from app.services.file_delivery_service import FileDeliveryNotFoundError, FileDeliveryService

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}/download")
async def download_file_by_id(
    file_id: str,
    session: AsyncSession = Depends(db_uow),
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    service = FileDeliveryService(session=session, repo_factory=repo_factory)
    try:
        resolved = await service.resolve(file_id, owner_id=str(current_user.id))
    except FileDeliveryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    payload = await s3_manager.get_object(bucket=resolved.bucket, key=resolved.key)
    if payload is None:
        raise HTTPException(status_code=404, detail="File not found")

    media_type = resolved.content_type or "application/octet-stream"
    headers = {
        "Content-Disposition": f'attachment; filename="{resolved.file_name}"',
    }
    return Response(content=payload, media_type=media_type, headers=headers)
