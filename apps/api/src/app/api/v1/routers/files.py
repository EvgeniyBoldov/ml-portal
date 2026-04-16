from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.repositories.factory import AsyncRepositoryFactory, get_async_repository_factory
from app.services.file_delivery_service import FileDeliveryService

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}/download")
async def download_file_by_id(
    file_id: str,
    session: AsyncSession = Depends(db_uow),
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    service = FileDeliveryService(session=session, repo_factory=repo_factory)
    resolved = await service.resolve(file_id, owner_id=str(current_user.id))
    url = await service.get_presigned_url(resolved)
    return RedirectResponse(url=url, status_code=307)
