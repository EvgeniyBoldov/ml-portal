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
        self._glossary = GlossaryService(session)
        self._projects = ProjectCatalogService(session)

    async def lookup(self, *, request_text: str, tenant_id: UUID | None) -> dict[str, Any]:
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
        return {
            "projects": matched_projects[:6], "glossary": matched_terms[:12], "entities": [],
            "ambiguities": [f"ambiguous_glossary_alias:{form}" for form in
                            ambiguous_glossary_aliases(request_text, glossary)],
        }
