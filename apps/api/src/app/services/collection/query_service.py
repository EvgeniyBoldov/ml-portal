from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.exceptions import CollectionNotFoundError
from app.models.collection import Collection, CollectionType
from app.models.rag_ingest import DocumentCollectionMembership


class CollectionQueryService:
    """Collection reads and lightweight stats updates."""

    def __init__(self, session: AsyncSession, host) -> None:
        self.session = session
        self.host = host

    async def get_by_id(self, collection_id: uuid.UUID) -> Optional[Collection]:
        result = await self.session.execute(
            select(Collection)
            .options(
                selectinload(Collection.schema),
                selectinload(Collection.current_version),
                selectinload(Collection.data_instance),
            )
            .where(Collection.id == collection_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Collection]:
        result = await self.session.execute(
            select(Collection)
            .options(
                selectinload(Collection.schema),
                selectinload(Collection.current_version),
                selectinload(Collection.data_instance),
            )
            .where(
                Collection.slug == slug,
                Collection.is_active.is_(True),
                Collection.lifecycle_status != "deprecated",
            )
        )
        return result.scalar_one_or_none()

    async def list_collections(self, tenant_id: uuid.UUID, active_only: bool = True) -> List[Collection]:
        query = select(Collection).where(Collection.tenant_id == tenant_id)
        query = query.options(
            selectinload(Collection.schema),
            selectinload(Collection.current_version),
            selectinload(Collection.data_instance),
        )
        if active_only:
            query = query.where(
                Collection.is_active == True,
                Collection.lifecycle_status != "deprecated",
            )
        query = query.order_by(Collection.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_row_count(self, collection_id: uuid.UUID) -> int:
        collection = await self.get_by_id(collection_id)
        if not collection:
            raise CollectionNotFoundError(f"Collection {collection_id} not found")

        result = await self.session.execute(text(f"SELECT COUNT(*) FROM {collection.table_name}"))
        count = result.scalar()

        collection.total_rows = count
        await self.host.sync_collection_status(collection, persist=False)
        await self.session.flush()
        return count

    async def get_effective_total_rows(self, collection: Collection) -> int:
        """Return actual row/document count for collection views."""
        if collection.collection_type == CollectionType.DOCUMENT.value:
            result = await self.session.execute(
                select(func.count())
                .select_from(DocumentCollectionMembership)
                .where(
                    DocumentCollectionMembership.tenant_id == collection.tenant_id,
                    DocumentCollectionMembership.collection_id == collection.id,
                )
            )
            return int(result.scalar() or 0)
        return int(collection.total_rows or 0)
