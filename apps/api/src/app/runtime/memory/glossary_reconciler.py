"""Candidate persistence for evidence-backed user, tenant and global terminology."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import (
    GlossaryEntry,
    GlossaryObservation,
    GlossaryScope,
    GlossaryStatus,
)
from app.models.memory import FactScope, FactSource
from app.runtime.memory.dto import FactDTO
from app.runtime.memory.decisions import MemoryDecision


GLOSSARY_CONFIRMATION_SUPPORT = 3


@dataclass(frozen=True)
class GlossaryReconciliationResult:
    changed: int
    decisions: list[MemoryDecision]


class GlossaryReconciler:
    """Persist glossary candidates and confirm only independently observed terms."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current_for(
        self,
        *,
        user_id: UUID | None,
        tenant_id: UUID | None,
    ) -> list[FactDTO]:
        owners = []
        owners.append(GlossaryEntry.scope == GlossaryScope.GLOBAL.value)
        if user_id is not None:
            owners.append(
                (GlossaryEntry.scope == GlossaryScope.USER.value)
                & (GlossaryEntry.user_id == user_id)
            )
        if tenant_id is not None:
            owners.append(
                (GlossaryEntry.scope == GlossaryScope.TENANT.value)
                & (GlossaryEntry.tenant_id == tenant_id)
            )
        if not owners:
            return []
        rows = await self._session.execute(
            select(GlossaryEntry).where(
                GlossaryEntry.is_active.is_(True),
                GlossaryEntry.status == GlossaryStatus.CONFIRMED.value,
                or_(*owners),
            )
        )
        return [
            FactDTO(
                id=row.id,
                # FactDTO is the existing compactor transport and its scopes
                # intentionally exclude global durable facts.  Global glossary
                # ownership is carried separately in metadata.
                scope=(
                    FactScope.TENANT
                    if row.scope == GlossaryScope.GLOBAL.value
                    else FactScope(row.scope)
                ),
                kind="glossary",
                subject=row.canonical_term,
                value=row.description or row.canonical_term,
                source=FactSource.SYSTEM,
                tenant_id=tenant_id,
                owner_type=row.scope,
                owner_id=(
                    row.user_id
                    if row.scope == GlossaryScope.USER.value
                    else row.tenant_id
                ),
                metadata={
                    "aliases": list(row.aliases or []),
                    "glossary_scope": row.scope,
                },
            )
            for row in rows.scalars().all()
        ]

    async def apply(
        self,
        *,
        candidates: Sequence[FactDTO],
        user_id: UUID | None,
        tenant_id: UUID | None,
    ) -> int:
        return (await self.apply_with_decisions(
            candidates=candidates, user_id=user_id, tenant_id=tenant_id,
        )).changed

    async def apply_with_decisions(
        self,
        *,
        candidates: Sequence[FactDTO],
        user_id: UUID | None,
        tenant_id: UUID | None,
    ) -> GlossaryReconciliationResult:
        changed = 0
        decisions: list[MemoryDecision] = []
        for candidate in candidates:
            if candidate.kind != "glossary":
                continue
            owner = _owner_for(
                candidate,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            if owner is None:
                decisions.append(MemoryDecision("fact_compactor", "reconciliation", "rejected", "missing_owner", (candidate,)))
                continue
            action = str(candidate.metadata.get("compaction_action") or "add")
            if action in {"discard", "mark_conflict"}:
                decisions.append(MemoryDecision(
                    "fact_compactor", "reconciliation",
                    "conflict" if action == "mark_conflict" else "rejected",
                    "marked_conflict" if action == "mark_conflict" else "discarded_by_compactor",
                    (candidate,), action=action,
                ))
                continue
            scope, owner_id = owner
            row = await self._find(scope=scope, owner_id=owner_id, canonical_term=candidate.subject)
            aliases = _aliases(candidate.metadata.get("aliases") or [], candidate.subject)
            if row is None:
                row = GlossaryEntry(
                    scope=scope.value,
                    user_id=owner_id if scope == GlossaryScope.USER else None,
                    tenant_id=owner_id if scope == GlossaryScope.TENANT else None,
                    canonical_term=candidate.subject,
                    aliases=aliases,
                    description=candidate.value,
                    status=GlossaryStatus.PENDING.value,
                    support_count=0,
                )
                self._session.add(row)
                await self._session.flush()
            else:
                row.is_active = True
                row.aliases = _aliases([*(row.aliases or []), *aliases], row.canonical_term)
                if row.status != GlossaryStatus.CONFIRMED.value:
                    row.description = candidate.value

            added = await self._add_observations(row, candidate.metadata.get("evidence") or [])
            if not added:
                decisions.append(MemoryDecision("fact_compactor", "reconciliation", "skipped", "no_new_evidence", (candidate,), action=action))
                continue
            now = datetime.now(timezone.utc)
            row.support_count += added
            if row.status != GlossaryStatus.CONFIRMED.value and row.support_count >= GLOSSARY_CONFIRMATION_SUPPORT:
                row.status = GlossaryStatus.CONFIRMED.value
                row.first_confirmed_at = row.first_confirmed_at or now
            if row.status == GlossaryStatus.CONFIRMED.value:
                row.last_confirmed_at = now
            self._session.add(row)
            changed += 1
            decisions.append(MemoryDecision(
                "fact_compactor", "publication", "published",
                "glossary_confirmed" if row.status == GlossaryStatus.CONFIRMED.value else "glossary_pending",
                (candidate,), action=action, status_after=str(row.status),
                support_after=int(row.support_count or 0), support_delta=added,
            ))
        await self._session.flush()
        return GlossaryReconciliationResult(changed, decisions)

    async def _find(
        self,
        *,
        scope: GlossaryScope,
        owner_id: UUID | None,
        canonical_term: str,
    ) -> GlossaryEntry | None:
        stmt = select(GlossaryEntry).where(
            GlossaryEntry.scope == scope.value,
            GlossaryEntry.canonical_term == canonical_term,
        )
        if scope == GlossaryScope.USER:
            stmt = stmt.where(GlossaryEntry.user_id == owner_id)
        elif scope == GlossaryScope.TENANT:
            stmt = stmt.where(GlossaryEntry.tenant_id == owner_id)
        else:
            stmt = stmt.where(
                GlossaryEntry.user_id.is_(None),
                GlossaryEntry.tenant_id.is_(None),
                GlossaryEntry.project_id.is_(None),
            )
        return (await self._session.execute(stmt.limit(1))).scalar_one_or_none()

    async def _add_observations(self, row: GlossaryEntry, raw: Sequence[object]) -> int:
        added = 0
        for item in raw:
            if not isinstance(item, dict):
                continue
            source_type = str(item.get("source_type") or "").strip()
            source_ref = str(item.get("support_ref") or item.get("source_ref") or "").strip()
            if not source_type or not source_ref:
                continue
            exists = await self._session.execute(
                select(GlossaryObservation.id).where(
                    GlossaryObservation.entry_id == row.id,
                    GlossaryObservation.source_type == source_type,
                    GlossaryObservation.source_ref == source_ref,
                )
            )
            if exists.scalar_one_or_none() is not None:
                continue
            self._session.add(GlossaryObservation(
                entry_id=row.id,
                source_type=source_type,
                source_ref=source_ref,
                source_label=_label(item.get("label")),
            ))
            await self._session.flush()
            added += 1
        return added


def _owner_for(
    candidate: FactDTO,
    *,
    user_id: UUID | None,
    tenant_id: UUID | None,
) -> tuple[GlossaryScope, UUID | None] | None:
    if candidate.kind == "glossary" and candidate.metadata.get("glossary_scope") == GlossaryScope.GLOBAL.value:
        return GlossaryScope.GLOBAL, None
    if candidate.scope == FactScope.USER and user_id is not None:
        return GlossaryScope.USER, user_id
    if candidate.scope == FactScope.TENANT and tenant_id is not None:
        return GlossaryScope.TENANT, tenant_id
    return None


def _aliases(raw: Sequence[object], canonical_term: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = {" ".join(canonical_term.strip().casefold().split())}
    for item in raw:
        value = " ".join(str(item or "").strip().split())[:255]
        normalized = value.casefold()
        if value and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def _label(value: Any) -> str | None:
    normalized = " ".join(str(value or "").strip().split())[:255]
    return normalized or None
