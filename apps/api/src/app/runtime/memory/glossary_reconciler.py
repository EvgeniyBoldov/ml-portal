"""Persistence adapter for LLM-normalized tenant terminology."""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryEntry, GlossaryScope
from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO


class GlossaryReconciler:
    """Stores compacted glossary entries; semantic decisions come from LLM."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current_for(self, *, tenant_id: UUID | None) -> list[FactDTO]:
        if tenant_id is None:
            return []
        rows = await self._session.execute(
            select(GlossaryEntry).where(
                GlossaryEntry.scope == GlossaryScope.TENANT.value,
                GlossaryEntry.tenant_id == tenant_id,
                GlossaryEntry.is_active.is_(True),
            )
        )
        return [
            FactDTO(
                id=row.id,
                scope=FactScope.TENANT,
                kind="glossary",
                subject=row.canonical_term,
                value=row.description or row.canonical_term,
                source=FactSource.SYSTEM,
                tenant_id=tenant_id,
                metadata={"aliases": list(row.aliases or [])},
            )
            for row in rows.scalars().all()
        ]

    async def apply(self, *, candidates: Sequence[FactDTO], tenant_id: UUID | None) -> int:
        if tenant_id is None:
            return 0
        changed = 0
        for candidate in candidates:
            if candidate.kind != "glossary" or candidate.scope != FactScope.TENANT:
                continue
            action = str(candidate.metadata.get("compaction_action") or "add")
            if action in {"discard", "mark_conflict"}:
                continue
            targets = _uuids(candidate.metadata.get("compaction_target_ids") or [])
            if action in {"rewrite", "supersede"} and targets:
                await self._session.execute(
                    update(GlossaryEntry)
                    .where(
                        GlossaryEntry.id.in_(targets),
                        GlossaryEntry.tenant_id == tenant_id,
                        GlossaryEntry.scope == GlossaryScope.TENANT.value,
                    )
                    .values(is_active=False)
                )
            row = (
                await self._session.execute(
                    select(GlossaryEntry).where(
                        GlossaryEntry.scope == GlossaryScope.TENANT.value,
                        GlossaryEntry.tenant_id == tenant_id,
                        GlossaryEntry.canonical_term == candidate.subject,
                    )
                )
            ).scalar_one_or_none()
            aliases = _aliases(candidate.metadata.get("aliases") or [])
            if row is None:
                row = GlossaryEntry(
                    scope=GlossaryScope.TENANT.value,
                    tenant_id=tenant_id,
                    canonical_term=candidate.subject,
                    aliases=aliases,
                    description=candidate.value,
                )
                self._session.add(row)
            else:
                row.is_active = True
                row.description = candidate.value
                row.aliases = _aliases([*(row.aliases or []), *aliases])
                self._session.add(row)
            changed += 1
        await self._session.flush()
        return changed


def _aliases(raw: Sequence[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value = " ".join(str(item or "").strip().split())[:255]
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def _uuids(raw: Sequence[object]) -> list[UUID]:
    result: list[UUID] = []
    for item in raw:
        try:
            result.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return result
