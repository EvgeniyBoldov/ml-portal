"""Cheap, deterministic terminology/project lookup for TurnPreflight."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.glossary_service import GlossaryService


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

    async def lookup(self, *, request_text: str, tenant_id: UUID | None) -> dict[str, Any]:
        projects, glossary = await self._glossary.list_project_terms(), await self._glossary.list_confirmed_terms(tenant_id=tenant_id)
        matched_projects = []
        for item in projects:
            matched = _matches(request_text, _forms(item, "key", "name", "aliases"))
            if matched:
                matched_projects.append({"id": str(item["id"]), "key": item["key"], "name": item["name"], "matched_aliases": matched})
        matched_terms = []
        entities = []
        for item in glossary:
            matched = _matches(request_text, _forms(item, "term", "aliases"))
            if not matched:
                continue
            matched_terms.append({
                "id": str(item["id"]), "term": item["term"],
                "aliases": list(item.get("aliases") or []), "matched_aliases": matched,
            })
            if item.get("entity_id"):
                entities.append({"id": str(item["entity_id"]), "type": item.get("entity_type"), "term": item["term"]})
        return {"projects": matched_projects[:6], "glossary": matched_terms[:12], "entities": entities[:12]}
