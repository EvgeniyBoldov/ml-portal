"""
Admin collection version endpoints.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, require_admin
from app.schemas.collections import (
    CollectionResponse,
    CollectionVersionCreate,
    CollectionVersionResponse,
    CollectionVersionUpdate,
)
from app.services.collection_service import CollectionService, _UNSET

from .collections_shared import build_collection_response

router = APIRouter()


def _serialize_version(entity) -> CollectionVersionResponse:
    return CollectionVersionResponse(
        id=entity.id,
        collection_id=entity.collection_id,
        version=entity.version,
        status=entity.status,
        semantic_profile=entity.semantic_profile or {},
        policy_hints=entity.policy_hints or {},
        notes=entity.notes,
        created_at=entity.created_at.isoformat(),
        updated_at=entity.updated_at.isoformat(),
    )


@router.get("/{collection_id}/versions", response_model=list[CollectionVersionResponse])
async def list_collection_versions(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    versions = await service.list_versions(collection_id)
    return [_serialize_version(v) for v in versions]


@router.get("/{collection_id}/versions/{version}", response_model=CollectionVersionResponse)
async def get_collection_version(
    collection_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    entity = await service.get_version(collection_id, version)
    if not entity:
        raise HTTPException(status_code=404, detail="Collection version not found")
    return _serialize_version(entity)


@router.post("/{collection_id}/versions", response_model=CollectionVersionResponse)
async def create_collection_version(
    collection_id: uuid.UUID,
    body: CollectionVersionCreate,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    created_version = await service.create_version(
        collection_id,
        semantic_profile=body.semantic_profile.model_dump(),
        policy_hints=body.policy_hints.model_dump(),
        notes=body.notes,
    )
    await session.commit()
    version_entity = await service.get_version(collection_id, created_version.version)
    return _serialize_version(version_entity)


@router.patch("/{collection_id}/versions/{version}", response_model=CollectionVersionResponse)
async def update_collection_version(
    collection_id: uuid.UUID,
    version: int,
    body: CollectionVersionUpdate,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    await service.update_version(
        collection_id,
        version,
        semantic_profile=body.semantic_profile.model_dump() if "semantic_profile" in body.model_fields_set and body.semantic_profile is not None else _UNSET,
        policy_hints=body.policy_hints.model_dump() if "policy_hints" in body.model_fields_set and body.policy_hints is not None else _UNSET,
        notes=body.notes if "notes" in body.model_fields_set else _UNSET,
    )
    await session.commit()
    entity = await service.get_version(collection_id, version)
    return _serialize_version(entity)


@router.post("/{collection_id}/versions/{version}/publish", response_model=CollectionVersionResponse)
async def publish_collection_version(
    collection_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    await service.publish_version(collection_id, version)
    await session.commit()
    entity = await service.get_version(collection_id, version)
    return _serialize_version(entity)


@router.post("/{collection_id}/versions/{version}/archive", response_model=CollectionVersionResponse)
async def archive_collection_version(
    collection_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    await service.archive_version(collection_id, version)
    await session.commit()
    entity = await service.get_version(collection_id, version)
    return _serialize_version(entity)


@router.put("/{collection_id}/current-version", response_model=CollectionResponse)
async def set_current_collection_version(
    collection_id: uuid.UUID,
    version_id: uuid.UUID = Query(..., description="Version ID to set as current"),
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.set_current_version(collection_id, version_id)
    await session.commit()
    await session.refresh(collection)
    return await build_collection_response(service, collection)
