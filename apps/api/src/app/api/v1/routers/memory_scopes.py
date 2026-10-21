"""Shared thematic scopes for HippoRAG; independent of collection access."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.schemas.memory_scope_preferences import MemoryScopeCatalogItem
from app.services.memory_scope_catalog import list_memory_scopes

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/scopes", response_model=list[MemoryScopeCatalogItem])
async def get_memory_scope_catalog(
    session: AsyncSession = Depends(db_uow),
    _user: UserCtx = Depends(get_current_user),
) -> list[MemoryScopeCatalogItem]:
    return [
        MemoryScopeCatalogItem.model_validate(scope)
        for scope in await list_memory_scopes(session)
    ]
