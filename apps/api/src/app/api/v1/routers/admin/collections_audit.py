"""
Admin collection audit and presets endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.impl.qdrant import QdrantVectorStore
from app.api.deps import db_uow, require_admin
from app.core.logging import get_logger
from app.models.collection import Collection
from app.schemas.collections import (
    CollectionTypePresetResponse,
    CollectionTypePresetsResponse,
    VectorCollectionAuditEntry,
    VectorCollectionAuditResponse,
)
from app.services.collection_service import CollectionService

logger = get_logger(__name__)

router = APIRouter()


@router.get("/vector-audit", response_model=VectorCollectionAuditResponse)
async def audit_qdrant_vector_collections(
    cleanup_orphans: bool = Query(False),
    orphan_prefix: str = Query("coll_"),
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    try:
        result = await session.execute(select(Collection).where(Collection.qdrant_collection_name.is_not(None)))
        registered = list(result.scalars().all())

        expected_map = {str(item.qdrant_collection_name): item for item in registered if item.qdrant_collection_name}
        expected_names = set(expected_map.keys())

        vector_store = QdrantVectorStore()
        qdrant_collections = await vector_store._client.get_collections()
        actual_names = {str(item.name) for item in qdrant_collections.collections}

        missing_entries: list[VectorCollectionAuditEntry] = []
        for name in sorted(expected_names - actual_names):
            item = expected_map[name]
            missing_entries.append(
                VectorCollectionAuditEntry(
                    qdrant_collection_name=name,
                    collection_id=item.id,
                    collection_slug=item.slug,
                    collection_type=item.collection_type,
                    detail="Qdrant collection not found for registered DB collection",
                )
            )

        non_vector_entries: list[VectorCollectionAuditEntry] = []
        for name, item in expected_map.items():
            if item.has_vector_search:
                continue
            non_vector_entries.append(
                VectorCollectionAuditEntry(
                    qdrant_collection_name=name,
                    collection_id=item.id,
                    collection_slug=item.slug,
                    collection_type=item.collection_type,
                    detail="Collection has qdrant_collection_name but has_vector_search=false",
                )
            )

        orphan_candidates = sorted(actual_names - expected_names)
        orphan_entries: list[VectorCollectionAuditEntry] = []
        cleaned_count = 0
        for name in orphan_candidates:
            if orphan_prefix and not name.startswith(orphan_prefix):
                continue
            orphan_entries.append(
                VectorCollectionAuditEntry(
                    qdrant_collection_name=name,
                    detail="Qdrant collection exists without DB collection reference",
                )
            )
            if cleanup_orphans:
                try:
                    await vector_store.delete_collection(name)
                    cleaned_count += 1
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "Failed to cleanup orphan Qdrant collection",
                        extra={"qdrant_collection_name": name, "error": str(exc)},
                    )

        return VectorCollectionAuditResponse(
            expected_count=len(expected_names),
            actual_count=len(actual_names),
            missing_in_qdrant=missing_entries,
            orphan_in_qdrant=orphan_entries,
            non_vector_with_qdrant=non_vector_entries,
            cleaned_orphan_count=cleaned_count,
        )
    except Exception as e:
        logger.error(f"Failed to audit Qdrant collections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to audit Qdrant collections: {str(e)}")


@router.get("/type-presets", response_model=CollectionTypePresetsResponse)
async def get_collection_type_presets(
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    presets = service.get_type_specific_field_presets()
    return CollectionTypePresetsResponse(
        items=[
            CollectionTypePresetResponse(collection_type=collection_type, fields=fields)
            for collection_type, fields in presets.items()
        ]
    )
