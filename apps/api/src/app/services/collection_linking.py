from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collection import Collection

_DOMAIN_BY_COLLECTION_TYPE = {
    "table": "collection.table",
    "document": "collection.document",
    "sql": "collection.sql",
    "api": "collection.api",
}


def runtime_domain_for_collection(
    *,
    collection: Optional[Collection],
    fallback_domain: str,
) -> str:
    if collection is None:
        return str(fallback_domain or "").strip()
    collection_type = str(collection.collection_type or "").strip().lower()
    return _DOMAIN_BY_COLLECTION_TYPE.get(collection_type, str(fallback_domain or "").strip())


def context_domain_for_collection(collection: Optional[Collection]) -> Optional[str]:
    if collection is None:
        return None
    collection_type = str(collection.collection_type or "").strip().lower()
    return _DOMAIN_BY_COLLECTION_TYPE.get(collection_type)


async def resolve_bound_collection_by_instance_id(
    session: AsyncSession,
    *,
    data_instance_id: UUID,
) -> Optional[Collection]:
    result = await session.execute(
        select(Collection)
        .options(
            selectinload(Collection.schema),
            selectinload(Collection.current_version),
        )
        .where(Collection.data_instance_id == data_instance_id)
        .order_by(Collection.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
