"""Glossary catalogue operations; matching is deliberately not part of v1."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryEntry, GlossaryObservation, GlossaryScope, GlossaryStatus
from app.models.project import Project


class GlossaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[GlossaryEntry]:
        rows = await self._session.execute(
            select(GlossaryEntry).where(GlossaryEntry.is_active.is_(True)).order_by(GlossaryEntry.canonical_term)
        )
        return list(rows.scalars().all())

    async def list_project_terms(self, *, limit: int | None = None) -> list[dict[str, object]]:
        """Thin glossary projection over the canonical project catalogue."""
        stmt = select(Project).where(Project.is_active.is_(True)).order_by(Project.name)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = await self._session.execute(stmt)
        return [
            {"id": item.id, "key": item.key, "name": item.name, "aliases": list(item.aliases or [])}
            for item in rows.scalars().all()
        ]

    async def list_confirmed_terms(self, *, tenant_id: UUID | None, limit: int | None = None) -> list[dict[str, object]]:
        """Terms visible to one department: global plus its own terminology.

        A local document is evidence for its tenant only; its terminology must
        not be promoted merely because extraction succeeded.
        """
        scope_filter = GlossaryEntry.scope == GlossaryScope.GLOBAL.value
        if tenant_id is not None:
            scope_filter = or_(
                scope_filter,
                (GlossaryEntry.scope == GlossaryScope.TENANT.value) & (GlossaryEntry.tenant_id == tenant_id),
            )
        rows = await self._session.execute(
            select(GlossaryEntry, GlossaryObservation)
            .outerjoin(GlossaryObservation, GlossaryObservation.entry_id == GlossaryEntry.id)
            .where(
                GlossaryEntry.is_active.is_(True),
                scope_filter,
            ).order_by(GlossaryEntry.canonical_term)
        )
        grouped: dict[UUID, tuple[GlossaryEntry, list[GlossaryObservation]]] = {}
        for entry, claim in rows.all():
            current = grouped.setdefault(entry.id, (entry, []))
            if claim is not None and claim.state == "active":
                current[1].append(claim)
        result: list[dict[str, object]] = []
        for entry, claims in grouped.values():
            # Legacy/manual entries without source claims retain their explicit
            # ownership contract. Document-derived entries must have at least
            # one source claim visible to this tenant.
            visible = [
                claim for claim in claims
                if claim.visibility_tenant_id is None or claim.visibility_tenant_id == tenant_id
            ]
            if claims and not visible:
                continue
            definitions = {str(claim.definition or "").strip() for claim in visible}
            if len(definitions) > 1:
                continue
            # A document-backed term is resolved from the caller-visible
            # evidence.  Its global aggregate status may include a private,
            # conflicting claim from another department and must not suppress
            # this tenant's consistent meaning.  Manual terms retain their
            # explicit confirmation gate.
            if not visible and entry.status != GlossaryStatus.CONFIRMED.value:
                continue
            winner = visible[0] if visible else None
            result.append({
                "id": entry.id, "term": entry.canonical_term,
                "description": (winner.definition if winner else entry.description) or entry.canonical_term,
                "aliases": list(winner.aliases if winner else entry.aliases or []), "scope": entry.scope,
                "entity_type": entry.entity_type, "entity_id": entry.entity_id,
                "project_id": entry.project_id,
            })
            if limit is not None and len(result) >= limit:
                break
        return result

    async def create(
        self,
        *,
        scope: GlossaryScope,
        canonical_term: str,
        aliases: list[str],
        entity_type: str,
        entity_id: str | None,
        description: str | None,
        tenant_id: UUID | None,
        project_id: UUID | None,
    ) -> GlossaryEntry:
        entry = GlossaryEntry(
            scope=scope.value,
            canonical_term=canonical_term,
            aliases=aliases,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
