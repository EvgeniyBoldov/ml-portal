"""Shared publication, source access and applicability predicates for memory reads."""
from __future__ import annotations

from uuid import UUID
from collections.abc import Sequence
from typing import Any
from sqlalchemy.sql.elements import ColumnElement

from sqlalchemy import and_, exists, false, or_, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.models.document_memory_staging import DocumentMemorySnapshot, MemoryExtractionCandidate
from app.models.memory import MemoryClaim, MemoryItem
from app.models.memory_scope import MemoryClaimScope, MemoryScope
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership


def published_claim(claim: Any = MemoryClaim) -> ColumnElement[bool]:
    """Only an approved current extraction may supply a live claim."""
    newer = aliased(DocumentMemorySnapshot)
    return and_(claim.state == "active", claim.lifecycle_status == "active", exists(
        select(MemoryExtractionCandidate.id).join(
            DocumentMemorySnapshot, DocumentMemorySnapshot.id == MemoryExtractionCandidate.snapshot_id,
        ).join(RAGDocument, RAGDocument.id == DocumentMemorySnapshot.document_id).where(
            MemoryExtractionCandidate.id == claim.approved_candidate_id,
            MemoryExtractionCandidate.resolution_status == "resolved",
            RAGDocument.status != "archived",
            MemoryExtractionCandidate.candidate_type != "term",
            MemoryExtractionCandidate.candidate_type == claim.item_type,
            DocumentMemorySnapshot.document_id == claim.document_id,
            DocumentMemorySnapshot.canonical_checksum == claim.canonical_checksum,
            DocumentMemorySnapshot.status.notin_(("superseded", "failed", "rejected")),
            or_(MemoryExtractionCandidate.attempt_id == DocumentMemorySnapshot.active_attempt_id,
                and_(MemoryExtractionCandidate.attempt_id.is_(None), DocumentMemorySnapshot.active_attempt_id.is_(None))),
            ~exists(select(newer.id).where(newer.document_id == DocumentMemorySnapshot.document_id,
                                           newer.created_at > DocumentMemorySnapshot.created_at)),
        ).correlate(claim),
    ))


async def allowed_source_collections(session: AsyncSession, *, user_id: UUID | None, tenant_id: UUID | None) -> list[UUID]:
    if user_id is None:
        return []
    from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
    from app.services.permission_service import PermissionService
    from app.services.platform_settings_service import PlatformSettingsProvider

    config = await PlatformSettingsProvider.get_instance().get_config(session)
    permissions = await RuntimeRbacResolver(PermissionService(session)).resolve_effective_permissions(
        user_id=user_id, tenant_id=tenant_id,
        default_collection_allow=bool(config.get("default_collection_allow", True)),
    )
    rows = (await session.execute(select(Collection.id, Collection.slug).where(
        Collection.is_active.is_(True), Collection.lifecycle_status == "active",
    ))).all()
    return [id_ for id_, slug in rows if permissions.is_collection_allowed(slug)]


def source_access(*, tenant_id: UUID | None, user_id: UUID | None = None,
                  collection_ids: Sequence[UUID] = ()) -> ColumnElement[bool]:
    collection_access = exists(select(DocumentCollectionMembership.id).where(
        DocumentCollectionMembership.source_id == RAGDocument.id,
        DocumentCollectionMembership.collection_id.in_(collection_ids),
    ).correlate(RAGDocument)) if collection_ids else false()
    access = [RAGDocument.scope == "global", and_(RAGDocument.scope == "collection", collection_access)]
    if tenant_id is not None:
        access.append(and_(RAGDocument.scope.in_(("tenant", "local")), RAGDocument.tenant_id == tenant_id))
    if user_id is not None:
        access.append(and_(RAGDocument.scope.in_(("user", "local")), RAGDocument.user_id == user_id))
    visibility = [MemoryClaim.visibility_tenant_id.is_(None)]
    if tenant_id is not None:
        visibility.append(MemoryClaim.visibility_tenant_id == tenant_id)
    # Source-bound tenant visibility follows an explicitly shared collection.
    visibility.append(and_(collection_access, MemoryClaim.visibility_tenant_id == RAGDocument.tenant_id))
    return and_(RAGDocument.status != "archived", or_(*access), or_(*visibility))


def _optional_values(column: Any, key: str, values: list[str]) -> ColumnElement[bool]:
    return or_(column[key].astext.is_(None), column[key] == [],
               *[column[key].contains([value]) for value in values])


def applicable_claim(*, project_ids: Sequence[UUID], scope_keys: Sequence[str], tenant_id: UUID | None) -> ColumnElement[bool]:
    """Filter scope groups before candidate limits; mirrors recall's final guard."""
    bindings = select(MemoryClaimScope.scope_id).join(MemoryScope, MemoryScope.id == MemoryClaimScope.scope_id).where(
        MemoryClaimScope.claim_id == MemoryClaim.id,
    ).correlate(MemoryClaim)
    predicates = []
    for scope_type in ("project", "team"):
        concrete = [key for key in scope_keys if key.startswith(f"{scope_type}.") and key != f"{scope_type}.all"]
        has_binding = exists(bindings.where(MemoryScope.scope_type == scope_type))
        match = [MemoryScope.key.in_(concrete), MemoryScope.is_all.is_(True)]
        if scope_type == "project" and project_ids:
            match.append(MemoryScope.project_id.in_(project_ids))
        matching = exists(bindings.where(
            MemoryScope.scope_type == scope_type, MemoryScope.lifecycle_status == "active", or_(*match),
        ))
        if scope_type == "team":
            predicates.append(or_(~has_binding, matching))
        elif "project.all" in scope_keys and not concrete and not project_ids:
            predicates.append(exists(bindings.where(MemoryScope.scope_type == "project",
                MemoryScope.lifecycle_status == "active", MemoryScope.is_all.is_(True))))
        elif concrete or project_ids:
            # Legacy project IDs remain actual project bindings, not null.
            predicates.append(or_(matching, and_(~has_binding, or_(MemoryClaim.project_id.in_(project_ids),
                *[MemoryClaim.applicability["project_ids"].contains([str(value)]) for value in project_ids]))))
        else:
            predicates.append(and_(~has_binding, MemoryClaim.project_id.is_(None)))
    predicates.append(~exists(bindings.where(MemoryScope.scope_type.notin_(("project", "team")))))
    tenants = [str(tenant_id)] if tenant_id else []
    predicates.extend([
        MemoryClaim.applicability.op("-")(array(["project_ids", "tenant_ids"])) == {},
        _optional_values(MemoryClaim.applicability, "project_ids", [str(id_) for id_ in project_ids]),
        _optional_values(MemoryClaim.applicability, "tenant_ids", tenants),
        MemoryItem.visibility.op("-")(array(["mode", "tenant_ids", "denied_tenant_ids"])) == {},
        or_(MemoryItem.visibility["mode"].astext.is_(None), MemoryItem.visibility["mode"].astext == "source"),
        _optional_values(MemoryItem.visibility, "tenant_ids", tenants),
    ])
    if tenants:
        predicates.append(~MemoryItem.visibility["denied_tenant_ids"].contains(tenants) | MemoryItem.visibility["denied_tenant_ids"].astext.is_(None))
    return and_(*predicates)


def live_item() -> ColumnElement[bool]:
    return and_(MemoryItem.state.in_(("active", "uncertain")), MemoryItem.lifecycle_status == "active",
                MemoryItem.item_type != "term",
                or_(and_(MemoryItem.scope == "company", MemoryItem.owner_type == "company"),
                    and_(MemoryItem.scope == "project", MemoryItem.owner_type == "project",
                         MemoryItem.owner_id == MemoryItem.project_id)))
