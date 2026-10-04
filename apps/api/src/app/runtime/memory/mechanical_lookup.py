"""Cheap, deterministic terminology/project lookup for TurnPreflight."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.glossary_service import (
    GlossaryService, ambiguous_glossary_aliases, matched_glossary_forms,
)
from app.services.project_catalog_service import ProjectCatalogService
from app.services.memory_scope_catalog import list_memory_scopes
from app.models.memory_scope import MemoryScopeGlossaryTerm
from app.models.document_memory_staging import GlossaryTerm
from sqlalchemy import select


def _forms(item: dict[str, Any], *keys: str) -> set[str]:
    values: set[str] = set()
    for key in keys:
        raw = item.get(key)
        if isinstance(raw, list):
            values.update(str(value).strip().lower() for value in raw if str(value).strip())
        elif str(raw or "").strip():
            values.add(str(raw).strip().lower())
    return values


def _matches(text: str, forms: set[str]) -> list[str]:
    normalized = f" {text.lower()} "
    return [
        form for form in sorted(forms)
        if form and re.search(rf"(?<!\w){re.escape(form)}(?!\w)", normalized)
    ]


class MechanicalLookupService:
    """Returns identifiers and aliases only; never durable-memory values."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._glossary = GlossaryService(session)
        self._projects = ProjectCatalogService(session)

    async def lookup(self, *, request_text: str | None = None, query: str | None = None,
                     tenant_id: UUID | None, scope_ceiling_keys: list[str] | None = None) -> dict[str, Any]:
        request_text = str(request_text or query or "").strip()
        projects, glossary = await self._projects.list_projects(), await self._glossary.list_confirmed_terms()
        matched_projects = []
        for item in projects:
            matched = _matches(request_text, _forms(item, "key", "name", "aliases"))
            if matched:
                matched_projects.append({"id": str(item["id"]), "key": item["key"], "name": item["name"], "matched_aliases": matched})
        matched_terms = []
        for item in glossary:
            matched = matched_glossary_forms(request_text, _forms(item, "term", "aliases"))
            if not matched:
                continue
            matched_terms.append({
                "id": str(item["id"]), "term": item["term"],
                "aliases": list(item.get("aliases") or []), "matched_aliases": matched,
            })
        scope_rows = await list_memory_scopes(self._session)
        linked = {}
        if scope_rows:
            links = (await self._session.execute(select(
                MemoryScopeGlossaryTerm.scope_id, GlossaryTerm.canonical_term, GlossaryTerm.aliases,
            ).join(GlossaryTerm, GlossaryTerm.id == MemoryScopeGlossaryTerm.glossary_term_id).where(
                MemoryScopeGlossaryTerm.scope_id.in_([row.id for row in scope_rows]),
                GlossaryTerm.id.in_(GlossaryService.published_terms_query().with_only_columns(GlossaryTerm.id)),
            ))).all()
            for scope_id, term, aliases in links:
                linked.setdefault(scope_id, []).extend([str(term), *(aliases or [])])
        candidates = []
        for row in scope_rows:
            if row.is_all:
                continue
            forms = {row.key, row.key.removeprefix(f"{row.scope_type}."), row.name,
                     *(row.aliases or []), *linked.get(row.id, [])}
            matched = _matches(request_text, {str(value).strip().casefold() for value in forms if str(value).strip()})
            if matched:
                candidates.append({"id": str(row.id), "key": row.key, "type": row.scope_type,
                                   "name": row.name, "aliases": list(row.aliases or []),
                                   "matched_forms": matched, "is_all": row.is_all})
        candidates.sort(key=lambda item: (0 if item["key"].casefold() in item["matched_forms"] else 1,
                                          -max(map(len, item["matched_forms"])), item["key"]))
        ceiling = set(scope_ceiling_keys or [])
        if scope_ceiling_keys is not None:
            candidates = [item for item in candidates if item["key"] in ceiling]
            matched_projects = [item for item in matched_projects if f"project.{item['key']}" in ceiling]
        return {
            "projects": matched_projects[:6], "glossary": matched_terms[:12], "entities": [],
            "scope_candidates": candidates[:40],
            "scope_candidates_truncated": len(candidates) > 40,
            "scope_ambiguities": [{"matched_form": form, "keys": sorted(item["key"] for item in candidates
                                      if form in item["matched_forms"])}
                                  for form in sorted({form for item in candidates for form in item["matched_forms"]})
                                  if sum(form in item["matched_forms"] for item in candidates) > 1],
            "ambiguities": [f"ambiguous_glossary_alias:{form}" for form in
                            ambiguous_glossary_aliases(request_text, glossary)],
        }
