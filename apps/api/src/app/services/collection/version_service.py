"""
CollectionVersionService — CRUD for CollectionVersion (semantic versioning).

Extracted from CollectionService to keep versioning logic self-contained.
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CollectionNotFoundError, InvalidSchemaError
from app.models.collection import (
    Collection,
    CollectionVersion,
    CollectionVersionStatus,
)


class CollectionVersionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Queries ───────────────────────────────────────────────────────────────

    async def list_versions(self, collection_id: UUID) -> List[CollectionVersion]:
        """List semantic versions for a collection, newest first."""
        result = await self.session.execute(
            select(CollectionVersion)
            .where(CollectionVersion.collection_id == collection_id)
            .order_by(CollectionVersion.version.desc())
        )
        return list(result.scalars().all())

    async def get_version(self, collection_id: UUID, version: int) -> CollectionVersion:
        """Get semantic version by collection + version number."""
        result = await self.session.execute(
            select(CollectionVersion).where(
                CollectionVersion.collection_id == collection_id,
                CollectionVersion.version == version,
            )
        )
        version_obj = result.scalar_one_or_none()
        if not version_obj:
            raise CollectionNotFoundError(
                f"Collection version {collection_id}:v{version} not found"
            )
        return version_obj

    # ── Mutations ─────────────────────────────────────────────────────────────

    async def create_version(
        self,
        collection_id: UUID,
        *,
        notes: str | None = None,
    ) -> CollectionVersion:
        """Create a new draft version."""
        max_version = await self.session.execute(
            select(func.max(CollectionVersion.version)).where(
                CollectionVersion.collection_id == collection_id
            )
        )
        next_version = (max_version.scalar() or 0) + 1

        version = CollectionVersion(
            collection_id=collection_id,
            version=next_version,
            status=CollectionVersionStatus.DRAFT.value,
            notes=notes,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def update_version(
        self,
        collection_id: UUID,
        version: int,
        *,
        notes: object = None,
        _UNSET: object = None,
    ) -> CollectionVersion:
        """Update fields of a draft version. Pass sentinel _UNSET to skip a field."""
        version_obj = await self.get_version(collection_id, version)
        if version_obj.status != CollectionVersionStatus.DRAFT.value:
            raise InvalidSchemaError("Only draft collection versions can be updated")

        if notes is not _UNSET and notes is not None:
            version_obj.notes = notes

        self.session.add(version_obj)
        await self.session.flush()
        return version_obj

    async def publish_version(self, collection_id: UUID, version: int) -> CollectionVersion:
        """Publish a draft version."""
        version_obj = await self.get_version(collection_id, version)
        if version_obj.status != CollectionVersionStatus.DRAFT.value:
            raise InvalidSchemaError(
                f"Only draft collection versions can be published (status: {version_obj.status})"
            )
        version_obj.status = CollectionVersionStatus.PUBLISHED.value
        self.session.add(version_obj)
        await self.session.flush()
        return version_obj

    async def archive_version(self, collection_id: UUID, version: int) -> CollectionVersion:
        """Archive a published version that is not the current primary."""
        collection = await self._get_collection(collection_id)
        version_obj = await self.get_version(collection_id, version)

        if version_obj.status != CollectionVersionStatus.PUBLISHED.value:
            raise InvalidSchemaError(
                f"Only published collection versions can be archived (status: {version_obj.status})"
            )
        if collection.current_version_id == version_obj.id:
            raise InvalidSchemaError(
                "Cannot archive a collection version currently linked as primary. "
                "Rebind another published version first."
            )

        version_obj.status = CollectionVersionStatus.ARCHIVED.value
        self.session.add(version_obj)
        await self.session.flush()
        return version_obj

    async def delete_version(self, collection_id: UUID, version: int) -> None:
        """Delete an archived or published version that is not the current primary."""
        collection = await self._get_collection(collection_id)
        version_obj = await self.get_version(collection_id, version)

        if version_obj.status not in {
            CollectionVersionStatus.PUBLISHED.value,
            CollectionVersionStatus.ARCHIVED.value,
        }:
            raise InvalidSchemaError(
                f"Only published or archived collection versions can be deleted "
                f"(status: {version_obj.status})"
            )
        if collection.current_version_id == version_obj.id:
            raise InvalidSchemaError(
                "Cannot delete a collection version currently linked as primary. "
                "Rebind another published version first."
            )

        await self.session.delete(version_obj)
        await self.session.flush()

    async def set_current_version(
        self, collection_id: UUID, version_id: UUID
    ) -> Collection:
        """Promote a published version to primary."""
        collection = await self._get_collection(collection_id)

        result = await self.session.execute(
            select(CollectionVersion).where(CollectionVersion.id == version_id)
        )
        version_obj = result.scalar_one_or_none()
        if not version_obj or version_obj.collection_id != collection_id:
            raise InvalidSchemaError(
                f"Version {version_id} not found for collection {collection_id}"
            )
        if version_obj.status != CollectionVersionStatus.PUBLISHED.value:
            raise InvalidSchemaError(
                f"Only published collection versions can be set as primary "
                f"(status: {version_obj.status})"
            )

        collection.current_version_id = version_obj.id
        self.session.add(collection)
        await self.session.flush()
        return collection

    # ── Factories ─────────────────────────────────────────────────────────────

    @staticmethod
    def build_initial_version(collection: Collection) -> CollectionVersion:
        """Build the v1 published version for a newly created collection."""
        return CollectionVersion(
            collection_id=collection.id,
            version=1,
            status=CollectionVersionStatus.PUBLISHED.value,
            retrieval_params={},
            prompt_context_params={},
            notes="Initial version",
        )

    # ── Backward compat aliases ───────────────────────────────────────────────

    async def activate_version(self, collection_id: UUID, version: int) -> CollectionVersion:
        return await self.publish_version(collection_id, version)

    async def deactivate_version(self, collection_id: UUID, version: int) -> CollectionVersion:
        return await self.archive_version(collection_id, version)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_collection(self, collection_id: UUID) -> Collection:
        result = await self.session.execute(
            select(Collection).where(Collection.id == collection_id)
        )
        collection = result.scalar_one_or_none()
        if not collection:
            raise CollectionNotFoundError(collection_id)
        return collection
