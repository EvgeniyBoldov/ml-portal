"""
Collection binding helpers.

Collection binding is an explicit runtime link stored in ToolInstance.config.
This module centralizes extraction and resolution so runtime behavior does not
depend on instance domain values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collection import Collection

COLLECTION_BINDING_TYPE = "collection_asset"
COLLECTION_TABLE_DOMAIN = "collection.table"
COLLECTION_DOCUMENT_DOMAIN = "collection.document"
COLLECTION_SQL_DOMAIN = "collection.sql"
COLLECTION_API_DOMAIN = "collection.api"


@dataclass(frozen=True)
class CollectionBindingRef:
    collection_id: Optional[UUID] = None
    collection_slug: Optional[str] = None
    tenant_id: Optional[UUID] = None


def extract_collection_binding(config: Optional[Dict[str, Any]]) -> Optional[CollectionBindingRef]:
    cfg = config or {}

    collection_id_raw = cfg.get("collection_id")
    collection_slug_raw = cfg.get("collection_slug")
    tenant_id_raw = cfg.get("tenant_id")
    binding_type = str(cfg.get("binding_type") or "").strip()

    # Binding must be explicit in v3 model.
    if binding_type != COLLECTION_BINDING_TYPE:
        return None

    collection_id: Optional[UUID] = None
    if collection_id_raw:
        try:
            collection_id = UUID(str(collection_id_raw))
        except (TypeError, ValueError):
            collection_id = None

    collection_slug = str(collection_slug_raw).strip() if collection_slug_raw else None
    tenant_id: Optional[UUID] = None
    if tenant_id_raw:
        try:
            tenant_id = UUID(str(tenant_id_raw))
        except (TypeError, ValueError):
            tenant_id = None

    if not collection_id and not (collection_slug and tenant_id):
        return None

    return CollectionBindingRef(
        collection_id=collection_id,
        collection_slug=collection_slug,
        tenant_id=tenant_id,
    )


def has_collection_binding(config: Optional[Dict[str, Any]]) -> bool:
    return extract_collection_binding(config) is not None


def resolve_collection_context_domain(
    config: Optional[Dict[str, Any]],
) -> Optional[str]:
    cfg = config or {}
    if has_collection_binding(cfg):
        collection_type = str(cfg.get("collection_type") or "").strip().lower()
        if collection_type == "table":
            return COLLECTION_TABLE_DOMAIN
        if collection_type == "document":
            return COLLECTION_DOCUMENT_DOMAIN
        if collection_type == "sql":
            return COLLECTION_SQL_DOMAIN
        if collection_type == "api":
            return COLLECTION_API_DOMAIN
    return None


def resolve_collection_runtime_domain(
    config: Optional[Dict[str, Any]],
    fallback_domain: str,
) -> str:
    """
    Resolve effective runtime domain for collection-bound instances.

    For collection-bound instances we prefer explicit collection_type from config,
    otherwise fall back to persisted instance.domain.
    """
    collection_domain = resolve_collection_context_domain(config)
    if collection_domain:
        return collection_domain
    return str(fallback_domain or "").strip()


async def resolve_bound_collection(
    session: AsyncSession,
    config: Optional[Dict[str, Any]],
) -> Optional[Collection]:
    binding = extract_collection_binding(config)
    if binding is None:
        return None

    if binding.collection_id:
        result = await session.execute(
            select(Collection)
            .options(
                selectinload(Collection.schema),
                selectinload(Collection.current_version),
            )
            .where(Collection.id == binding.collection_id)
        )
        collection = result.scalar_one_or_none()
        if collection:
            return collection

    if binding.collection_slug and binding.tenant_id:
        result = await session.execute(
            select(Collection)
            .options(
                selectinload(Collection.schema),
                selectinload(Collection.current_version),
            )
            .where(
                Collection.slug == binding.collection_slug,
                Collection.tenant_id == binding.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    return None
