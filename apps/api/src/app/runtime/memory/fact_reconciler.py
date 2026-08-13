"""Deterministic persistence for compacted fact candidates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Fact, FactObservation, FactScope, FactStatus
from app.models.memory import FactSource
from app.models.project import Project
from app.runtime.memory.dto import FactDTO


class FactReconciler:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def current_for(
        self,
        *,
        user_id: UUID | None,
        tenant_id: UUID | None,
        project_keys: Sequence[str] = (),
    ) -> list[FactDTO]:
        owners = []
        if user_id:
            owners.append((Fact.owner_type == "user") & (Fact.owner_id == user_id))
        if tenant_id:
            owners.append((Fact.owner_type == "tenant") & (Fact.owner_id == tenant_id))
        normalized_keys = {key.strip().lower() for key in project_keys if key and key.strip()}
        if normalized_keys:
            projects = await self._session.execute(select(Project.id).where(Project.key.in_(normalized_keys)))
            project_ids = [row for row in projects.scalars().all()]
            if project_ids:
                owners.append(Fact.project_id.in_(project_ids))
        if not owners:
            return []
        rows = await self._session.execute(select(Fact).where(Fact.superseded_by.is_(None), or_(*owners)))
        # The compactor only needs a bounded contextual view.  Tenant/project
        # candidates carry their own grouping and are resolved during apply.
        return [_dto(row) for row in rows.scalars().all()]

    async def ensure_projects(self, candidates: Sequence[FactDTO]) -> None:
        """Create catalogue rows for evidenced project facts when absent.

        Project names are LLM-normalised only after extractor evidence
        validation, therefore this operation never creates a project from an
        agent conclusion alone.
        """
        for candidate in candidates:
            if candidate.scope != FactScope.PROJECT:
                continue
            key = str(candidate.metadata.get("project_key") or "").strip().lower()
            if not key:
                continue
            exists = await self._session.execute(select(Project.id).where(Project.key == key))
            if exists.scalar_one_or_none() is None:
                self._session.add(Project(key=key, name=key, aliases=[key]))
        await self._session.flush()

    async def apply(
        self,
        *,
        candidates: Sequence[FactDTO],
        user_id: UUID | None,
        tenant_id: UUID | None,
        sandbox: bool = False,
    ) -> int:
        await self.ensure_projects(candidates)
        changed = 0
        for candidate in candidates:
            compaction_action = str(candidate.metadata.get("compaction_action") or "add")
            owner_type, owner_id, project_id = await self._owner_for(candidate, user_id=user_id, tenant_id=tenant_id)
            if owner_id is None and project_id is None:
                continue
            existing = await self._find_same(
                candidate, owner_type=owner_type, owner_id=owner_id, project_id=project_id,
            )
            if existing is None:
                existing = Fact(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    owner_type=owner_type,
                    owner_id=owner_id,
                    kind=candidate.kind,
                    entry_metadata=_persisted_metadata(candidate.metadata),
                    scope=candidate.scope.value,
                    subject=candidate.subject,
                    value=candidate.value,
                    normalized_value=_normalized(candidate.value),
                    confidence=candidate.confidence,
                    source=candidate.source.value,
                    source_ref=None,
                    observed_at=candidate.observed_at,
                    user_visible=candidate.scope == FactScope.USER,
                    status=(FactStatus.CONFIRMED.value if sandbox or candidate.scope == FactScope.USER else FactStatus.PENDING.value),
                    support_count=0,
                )
                self._session.add(existing)
                await self._session.flush()
                if compaction_action in {"rewrite", "supersede"}:
                    await self._supersede_targets(existing, candidate.metadata.get("compaction_target_ids") or [])
            added = await self._add_observations(existing, candidate.metadata.get("evidence") or [])
            if not added:
                continue
            existing.support_count += added
            existing.observed_at = datetime.now(timezone.utc)
            marked_project_fact = bool(candidate.metadata.get("project_memory_marked"))
            if compaction_action == "mark_conflict":
                existing.status = FactStatus.UNCONFIRMED.value
            elif sandbox or existing.scope == FactScope.USER or marked_project_fact:
                existing.status = FactStatus.CONFIRMED.value
                existing.first_confirmed_at = existing.first_confirmed_at or datetime.now(timezone.utc)
                existing.last_confirmed_at = datetime.now(timezone.utc)
            elif existing.support_count >= 3:
                existing.status = FactStatus.CONFIRMED.value
                existing.first_confirmed_at = existing.first_confirmed_at or datetime.now(timezone.utc)
                existing.last_confirmed_at = datetime.now(timezone.utc)
            if existing.scope == FactScope.PROJECT.value and existing.status == FactStatus.CONFIRMED.value:
                await self._apply_confirmed_project_aliases(existing, candidate.metadata.get("project_aliases") or [])
            self._session.add(existing)
            changed += 1
        await self._session.flush()
        return changed

    async def _apply_confirmed_project_aliases(self, fact: Fact, raw_aliases: Sequence[object]) -> None:
        if fact.project_id is None:
            return
        row = await self._session.execute(select(Project).where(Project.id == fact.project_id))
        project = row.scalar_one_or_none()
        if project is None:
            return
        aliases = list(project.aliases or [])
        known = {item.casefold() for item in aliases}
        for raw in raw_aliases:
            alias = " ".join(str(raw or "").strip().split())[:120]
            if alias and alias.casefold() not in known and alias.casefold() != project.name.casefold():
                aliases.append(alias)
                known.add(alias.casefold())
        project.aliases = aliases
        self._session.add(project)

    async def _owner_for(self, candidate: FactDTO, *, user_id: UUID | None, tenant_id: UUID | None) -> tuple[str | None, UUID | None, UUID | None]:
        if candidate.scope == FactScope.USER:
            return "user", user_id, None
        if candidate.scope == FactScope.TENANT:
            return "tenant", tenant_id, None
        project_key = str(candidate.metadata.get("project_key") or "").strip().lower()
        if not project_key:
            return None, None, None
        row = await self._session.execute(select(Project).where(Project.key == project_key, Project.is_active.is_(True)))
        project = row.scalar_one_or_none()
        return ("project", project.id, project.id) if project else (None, None, None)

    async def _find_same(self, candidate: FactDTO, *, owner_type: str | None, owner_id: UUID | None, project_id: UUID | None) -> Fact | None:
        stmt = select(Fact).where(
            Fact.scope == candidate.scope.value,
            Fact.subject == candidate.subject,
            Fact.normalized_value == _normalized(candidate.value),
            Fact.superseded_by.is_(None),
        )
        stmt = stmt.where(Fact.project_id == project_id) if project_id else stmt.where(Fact.owner_type == owner_type, Fact.owner_id == owner_id)
        return (await self._session.execute(stmt.limit(1))).scalar_one_or_none()

    async def _demote_conflicts(self, inserted: Fact) -> None:
        stmt = update(Fact).where(
            Fact.id != inserted.id,
            Fact.scope == inserted.scope,
            Fact.subject == inserted.subject,
            Fact.superseded_by.is_(None),
            Fact.status == FactStatus.CONFIRMED.value,
        ).values(status=FactStatus.UNCONFIRMED.value)
        stmt = stmt.where(Fact.project_id == inserted.project_id) if inserted.project_id else stmt.where(Fact.owner_type == inserted.owner_type, Fact.owner_id == inserted.owner_id)
        await self._session.execute(stmt)

    async def _supersede_targets(self, replacement: Fact, raw_ids: Sequence[object]) -> None:
        """Apply an LLM-selected semantic replacement without key heuristics."""
        ids: list[UUID] = []
        for raw in raw_ids:
            try:
                parsed = UUID(str(raw))
            except (TypeError, ValueError):
                continue
            if parsed != replacement.id:
                ids.append(parsed)
        if not ids:
            return
        stmt = update(Fact).where(
            Fact.id.in_(ids),
            Fact.superseded_by.is_(None),
            Fact.scope == replacement.scope,
        )
        stmt = stmt.where(Fact.project_id == replacement.project_id) if replacement.project_id else stmt.where(
            Fact.owner_type == replacement.owner_type, Fact.owner_id == replacement.owner_id,
        )
        await self._session.execute(stmt.values(superseded_by=replacement.id))

    async def _add_observations(self, fact: Fact, raw: Sequence[dict[str, Any]]) -> int:
        added = 0
        for item in raw:
            source_type, source_ref = str(item.get("source_type") or ""), str(item.get("source_ref") or "")
            if not source_type or not source_ref:
                continue
            exists = await self._session.execute(select(FactObservation.id).where(
                FactObservation.fact_id == fact.id,
                FactObservation.source_type == source_type,
                FactObservation.source_ref == source_ref,
            ))
            if exists.scalar_one_or_none() is not None:
                continue
            observation = FactObservation(fact_id=fact.id, source_type=source_type, source_ref=source_ref, source_label=item.get("label"))
            self._session.add(observation)
            await self._session.flush()
            added += 1
        return added

    async def replace_user_fact(self, *, fact_id: UUID, user_id: UUID, subject: str, value: str) -> Fact | None:
        """Create an immutable, immediately-confirmed manual revision."""
        current = await self._session.execute(select(Fact).where(
            Fact.id == fact_id,
            Fact.owner_type == "user",
            Fact.owner_id == user_id,
            Fact.superseded_by.is_(None),
        ))
        previous = current.scalar_one_or_none()
        if previous is None:
            return None
        now = datetime.now(timezone.utc)
        await self._session.execute(update(Fact).where(
            Fact.owner_type == "user", Fact.owner_id == user_id,
            Fact.scope == FactScope.USER.value, Fact.subject == subject,
            Fact.superseded_by.is_(None), Fact.id != fact_id,
        ).values(status=FactStatus.UNCONFIRMED.value))
        previous.status = FactStatus.UNCONFIRMED.value
        replacement = Fact(
            tenant_id=previous.tenant_id,
            owner_type="user",
            owner_id=user_id,
            kind=previous.kind,
            scope=FactScope.USER.value,
            subject=subject,
            value=value,
            normalized_value=_normalized(value),
            confidence=1.0,
            source=FactSource.MANUAL.value,
            source_ref=f"manual:{fact_id}",
            observed_at=now,
            user_visible=True,
            status=FactStatus.CONFIRMED.value,
            support_count=1,
            first_confirmed_at=now,
            last_confirmed_at=now,
            revision=previous.revision + 1,
        )
        self._session.add(replacement)
        await self._session.flush()
        self._session.add(FactObservation(
            fact_id=replacement.id,
            source_type=FactSource.MANUAL.value,
            source_ref=f"manual:{fact_id}",
            source_label="Manual profile edit",
        ))
        await self._session.flush()
        return replacement


def _normalized(value: str) -> str:
    return " ".join((value or "").lower().split())[:500]


def _dto(row: Fact) -> FactDTO:
    from app.models.memory import FactSource
    return FactDTO(
        scope=FactScope(row.scope),
        subject=row.subject,
        value=row.value,
        source=FactSource(row.source),
        tenant_id=row.tenant_id,
        project_id=row.project_id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        kind=row.kind or "fact",
        metadata=dict(row.entry_metadata or {}),
        confidence=row.confidence,
    )


def _persisted_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Keep routing/conflict metadata, while observations retain provenance."""
    result = {
        key: metadata[key]
        for key in ("project_key", "project_aliases", "aliases", "compaction_action")
        if metadata.get(key) not in (None, "", [])
    }
    return result or None
