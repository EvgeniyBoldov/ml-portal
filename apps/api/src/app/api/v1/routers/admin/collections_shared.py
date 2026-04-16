"""
Shared helpers for admin collection routers.
"""
from __future__ import annotations

from app.schemas.collections import CollectionResponse, CollectionVersionResponse
from app.services.collection_service import CollectionService


async def build_collection_response(service: CollectionService, collection) -> CollectionResponse:
    current_version_payload = None
    if collection.current_version:
        current_version_payload = CollectionVersionResponse(
            id=collection.current_version.id,
            collection_id=collection.current_version.collection_id,
            version=collection.current_version.version,
            status=collection.current_version.status,
            semantic_profile=collection.current_version.semantic_profile or {},
            policy_hints=collection.current_version.policy_hints or {},
            notes=collection.current_version.notes,
            created_at=collection.current_version.created_at.isoformat(),
            updated_at=collection.current_version.updated_at.isoformat(),
        )

    snapshot = await service.sync_collection_status(collection, persist=False)
    return CollectionResponse(
        id=collection.id,
        tenant_id=collection.tenant_id,
        collection_type=collection.collection_type,
        slug=collection.slug,
        name=collection.name,
        description=collection.description,
        fields=collection.fields,
        source_contract=collection.source_contract,
        status=snapshot["status"],
        status_details=snapshot["details"],
        table_name=collection.table_name,
        table_schema=collection.table_schema,
        has_vector_search=collection.has_vector_search,
        vector_config=collection.vector_config,
        qdrant_collection_name=collection.qdrant_collection_name,
        total_rows=collection.total_rows,
        vectorized_rows=collection.vectorized_rows,
        total_chunks=collection.total_chunks,
        failed_rows=collection.failed_rows,
        vectorization_progress=collection.vectorization_progress,
        is_fully_vectorized=collection.is_fully_vectorized,
        data_instance_id=collection.data_instance_id,
        last_sync_at=collection.last_sync_at.isoformat() if collection.last_sync_at else None,
        is_active=collection.is_active,
        current_version_id=collection.current_version_id,
        current_version=current_version_payload,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
    )
