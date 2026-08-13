"""Admin read/write API for user-owned and tenant-owned facts."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.schemas.memory import AdminFactCreate, AdminFactResponse, AdminFactUpdate
from app.services.fact_admin_service import AdminFactNotFoundError, FactAdminService

router = APIRouter(tags=["facts"])


def _response(fact) -> AdminFactResponse:
    return AdminFactResponse(
        id=fact.id,
        owner_type=fact.owner_type,
        owner_id=fact.owner_id,
        scope=fact.scope,
        subject=fact.subject,
        value=fact.value,
        confidence=fact.confidence,
        source=fact.source,
        status=fact.status,
        support_count=fact.support_count,
        observed_at=fact.observed_at,
        created_at=fact.created_at,
    )


async def _list(
    *, owner_type: str, owner_id: UUID, db: AsyncSession,
) -> list[AdminFactResponse]:
    return [_response(fact) for fact in await FactAdminService(db).list(owner_type=owner_type, owner_id=owner_id)]


async def _create(
    *, owner_type: str, owner_id: UUID, payload: AdminFactCreate, db: AsyncSession,
) -> AdminFactResponse:
    fact = await FactAdminService(db).create(
        owner_type=owner_type, owner_id=owner_id, subject=payload.subject, value=payload.value,
    )
    await db.commit()
    await db.refresh(fact)
    return _response(fact)


async def _update(
    *, owner_type: str, owner_id: UUID, fact_id: UUID, payload: AdminFactUpdate, db: AsyncSession,
) -> AdminFactResponse:
    try:
        fact = await FactAdminService(db).update(
            fact_id=fact_id, owner_type=owner_type, owner_id=owner_id,
            subject=payload.subject, value=payload.value,
        )
    except AdminFactNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found") from exc
    await db.commit()
    await db.refresh(fact)
    return _response(fact)


async def _delete(
    *, owner_type: str, owner_id: UUID, fact_id: UUID, db: AsyncSession,
) -> None:
    try:
        await FactAdminService(db).delete(fact_id=fact_id, owner_type=owner_type, owner_id=owner_id)
    except AdminFactNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found") from exc
    await db.commit()


@router.get("/users/{user_id}/facts", response_model=list[AdminFactResponse])
async def list_user_facts(user_id: UUID, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    return await _list(owner_type="user", owner_id=user_id, db=db)


@router.post("/users/{user_id}/facts", response_model=AdminFactResponse, status_code=status.HTTP_201_CREATED)
async def create_user_fact(user_id: UUID, payload: AdminFactCreate, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    return await _create(owner_type="user", owner_id=user_id, payload=payload, db=db)


@router.put("/users/{user_id}/facts/{fact_id}", response_model=AdminFactResponse)
async def update_user_fact(user_id: UUID, fact_id: UUID, payload: AdminFactUpdate, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    return await _update(owner_type="user", owner_id=user_id, fact_id=fact_id, payload=payload, db=db)


@router.delete("/users/{user_id}/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_fact(user_id: UUID, fact_id: UUID, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    await _delete(owner_type="user", owner_id=user_id, fact_id=fact_id, db=db)


@router.get("/tenants/{tenant_id}/facts", response_model=list[AdminFactResponse])
async def list_tenant_facts(tenant_id: UUID, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    return await _list(owner_type="tenant", owner_id=tenant_id, db=db)


@router.post("/tenants/{tenant_id}/facts", response_model=AdminFactResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant_fact(tenant_id: UUID, payload: AdminFactCreate, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    return await _create(owner_type="tenant", owner_id=tenant_id, payload=payload, db=db)


@router.put("/tenants/{tenant_id}/facts/{fact_id}", response_model=AdminFactResponse)
async def update_tenant_fact(tenant_id: UUID, fact_id: UUID, payload: AdminFactUpdate, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    return await _update(owner_type="tenant", owner_id=tenant_id, fact_id=fact_id, payload=payload, db=db)


@router.delete("/tenants/{tenant_id}/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant_fact(tenant_id: UUID, fact_id: UUID, db: AsyncSession = Depends(db_session), _: object = Depends(require_admin)):
    await _delete(owner_type="tenant", owner_id=tenant_id, fact_id=fact_id, db=db)

