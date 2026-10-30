"""Tenant-role policy for editing collection content."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.models.collection import Collection
from app.models.rag_ingest import DocumentCollectionMembership
from app.models.tenant import Tenants, UserTenants
from app.services.permission_service import PermissionService


@dataclass(frozen=True)
class DocumentContentAccess:
    linked_to_collection: bool
    allowed: bool
    reason: str | None = None


class CollectionContentAccessService:
    """Resolve content edit rights from current tenant membership and collection ACL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def edit_access_reason(self, user_id: UUID, tenant_id: UUID) -> str | None:
        row = (await self.session.execute(
            select(
                Tenants.is_active,
                Tenants.lifecycle_status,
                UserTenants.is_tenant_admin,
                UserTenants.is_data_editor,
            )
            .select_from(Tenants)
            .outerjoin(
                UserTenants,
                (UserTenants.tenant_id == Tenants.id) & (UserTenants.user_id == user_id),
            )
            .where(Tenants.id == tenant_id)
        )).one_or_none()
        if row is None or not row.is_active or row.lifecycle_status == "deprecated":
            return "tenant_inactive"
        if not (row.is_tenant_admin or row.is_data_editor):
            return "editing_permission_required"
        return None

    async def can_edit_tenant(self, user_id: UUID, tenant_id: UUID) -> bool:
        return await self.edit_access_reason(user_id, tenant_id) is None

    async def document_write_access(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        document_tenant_id: UUID | None,
    ) -> DocumentContentAccess:
        rows = (await self.session.execute(
            select(
                DocumentCollectionMembership.tenant_id,
                Collection.tenant_id,
                Collection.slug,
                Collection.is_active,
                Collection.lifecycle_status,
            )
            .join(Collection, Collection.id == DocumentCollectionMembership.collection_id)
            .where(DocumentCollectionMembership.source_id == document_id)
        )).all()
        if not rows:
            return DocumentContentAccess(linked_to_collection=False, allowed=True)

        if any(membership_tenant_id != document_tenant_id or collection_tenant_id != document_tenant_id
               for membership_tenant_id, collection_tenant_id, *_ in rows):
            return DocumentContentAccess(
                linked_to_collection=True,
                allowed=False,
                reason="collection_membership_mismatch",
            )

        role_reason = await self.edit_access_reason(user_id, document_tenant_id)
        if role_reason:
            return DocumentContentAccess(
                linked_to_collection=True,
                allowed=False,
                reason=role_reason,
            )

        if any(not is_active or lifecycle_status == "deprecated"
               for _, _, _, is_active, lifecycle_status in rows):
            return DocumentContentAccess(
                linked_to_collection=True,
                allowed=False,
                reason="collection_inactive",
            )

        resolver = RuntimeRbacResolver(PermissionService(self.session))
        permissions = await resolver.resolve_effective_permissions(
            user_id=user_id,
            tenant_id=document_tenant_id,
            default_collection_allow=True,
        )
        for _, _, collection_slug, _, _ in rows:
            if not resolver.is_collection_allowed(
                effective_permissions=permissions,
                collection_slug=collection_slug,
            ):
                return DocumentContentAccess(
                    linked_to_collection=True,
                    allowed=False,
                    reason="collection_access_denied",
                )
        return DocumentContentAccess(linked_to_collection=True, allowed=True)
