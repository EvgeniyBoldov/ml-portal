from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.models.credential_set import Credential
from app.models.memory import Fact
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership, Source
from app.models.tenant import UserTenants


@dataclass
class MigrationReport:
    from_tenant_id: uuid.UUID
    to_tenant_id: uuid.UUID
    migrated: dict[str, int] = field(default_factory=dict)
    renamed_collections: list[tuple[str, str]] = field(default_factory=list)


class TenantMigrationService:
    """Migrate tenant-owned data to target tenant before hard delete."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def migrate_tenant_data(
        self,
        *,
        from_tenant_id: uuid.UUID,
        to_tenant_id: uuid.UUID,
    ) -> MigrationReport:
        if from_tenant_id == to_tenant_id:
            return MigrationReport(from_tenant_id=from_tenant_id, to_tenant_id=to_tenant_id)

        report = MigrationReport(from_tenant_id=from_tenant_id, to_tenant_id=to_tenant_id)

        report.migrated["user_tenants"] = await self._migrate_user_tenants(
            from_tenant_id=from_tenant_id,
            to_tenant_id=to_tenant_id,
        )
        moved_collections, renamed = await self._migrate_collections(
            from_tenant_id=from_tenant_id,
            to_tenant_id=to_tenant_id,
        )
        report.migrated["collections"] = moved_collections
        report.renamed_collections = renamed

        report.migrated["ragdocuments"] = await self._bulk_reassign(
            model=RAGDocument,
            from_tenant_id=from_tenant_id,
            to_tenant_id=to_tenant_id,
        )
        report.migrated["sources"] = await self._bulk_reassign(
            model=Source,
            from_tenant_id=from_tenant_id,
            to_tenant_id=to_tenant_id,
        )
        report.migrated["document_collection_memberships"] = await self._bulk_reassign(
            model=DocumentCollectionMembership,
            from_tenant_id=from_tenant_id,
            to_tenant_id=to_tenant_id,
        )
        report.migrated["credentials"] = await self._bulk_reassign_owner_tenant_credentials(
            from_tenant_id=from_tenant_id,
            to_tenant_id=to_tenant_id,
        )
        report.migrated["tenant_facts"] = await self._bulk_reassign_fact_tenant(
            from_tenant_id=from_tenant_id,
            to_tenant_id=to_tenant_id,
        )

        return report

    async def _migrate_user_tenants(self, *, from_tenant_id: uuid.UUID, to_tenant_id: uuid.UUID) -> int:
        rows = (
            await self.session.execute(
                select(UserTenants).where(UserTenants.tenant_id == from_tenant_id)
            )
        ).scalars().all()
        moved = 0
        for row in rows:
            existing = (
                await self.session.execute(
                    select(UserTenants).where(
                        UserTenants.user_id == row.user_id,
                        UserTenants.tenant_id == to_tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                await self.session.delete(row)
                continue
            row.tenant_id = to_tenant_id
            row.is_default = bool(row.is_default)
            moved += 1
        await self.session.flush()
        return moved

    async def _migrate_collections(
        self,
        *,
        from_tenant_id: uuid.UUID,
        to_tenant_id: uuid.UUID,
    ) -> tuple[int, list[tuple[str, str]]]:
        rows = (
            await self.session.execute(
                select(Collection).where(Collection.tenant_id == from_tenant_id)
            )
        ).scalars().all()
        moved = 0
        renamed: list[tuple[str, str]] = []
        short = str(from_tenant_id).replace("-", "")[:8]

        for row in rows:
            original_slug = row.slug
            target_slug = original_slug
            suffix = 1
            while True:
                conflict = (
                    await self.session.execute(
                        select(Collection.id).where(
                            Collection.tenant_id == to_tenant_id,
                            Collection.slug == target_slug,
                            Collection.id != row.id,
                        )
                    )
                ).scalar_one_or_none()
                if not conflict:
                    break
                suffix += 1
                target_slug = f"t_{short}__{original_slug}_{suffix}"[:100]

            if target_slug != original_slug:
                row.slug = target_slug
                renamed.append((original_slug, target_slug))

            row.tenant_id = to_tenant_id
            moved += 1

        await self.session.flush()
        return moved, renamed

    async def _bulk_reassign(self, *, model, from_tenant_id: uuid.UUID, to_tenant_id: uuid.UUID) -> int:
        rows = (
            await self.session.execute(select(model).where(model.tenant_id == from_tenant_id))
        ).scalars().all()
        for row in rows:
            row.tenant_id = to_tenant_id
        await self.session.flush()
        return len(rows)

    async def _bulk_reassign_owner_tenant_credentials(
        self,
        *,
        from_tenant_id: uuid.UUID,
        to_tenant_id: uuid.UUID,
    ) -> int:
        rows = (
            await self.session.execute(
                select(Credential).where(Credential.owner_tenant_id == from_tenant_id)
            )
        ).scalars().all()
        for row in rows:
            row.owner_tenant_id = to_tenant_id
        await self.session.flush()
        return len(rows)

    async def _bulk_reassign_fact_tenant(self, *, from_tenant_id: uuid.UUID, to_tenant_id: uuid.UUID) -> int:
        rows = (
            await self.session.execute(select(Fact).where(Fact.tenant_id == from_tenant_id))
        ).scalars().all()
        for row in rows:
            row.tenant_id = to_tenant_id
        await self.session.flush()
        return len(rows)
