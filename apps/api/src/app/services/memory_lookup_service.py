"""Bounded glossary expansion and project-memory key discovery."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any, Iterable, Sequence
from uuid import UUID

from app.models.memory import Fact
from app.models.project import Project
from app.repositories.memory_lookup_repository import MemoryLookupRepository


MAX_GLOSSARY_ROWS = 250
MAX_PROJECT_ROWS = 250
MAX_PROJECTS = 8
MAX_KEYS_PER_PROJECT = 12


def normalize_memory_term(value: str) -> str:
    """Normalize user-facing aliases without relying on an LLM."""
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def _unique_terms(values: Iterable[str], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value).split())
        normalized = normalize_memory_term(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
        if len(result) == limit:
            break
    return result


def _matching_forms(project: Project) -> set[str]:
    return {
        item for item in (
            normalize_memory_term(project.key),
            normalize_memory_term(project.name),
            *(normalize_memory_term(alias) for alias in project.aliases or []),
        ) if item
    }


class MemoryLookupService:
    """Resolve user language to glossary entries, projects, and memory keys.

    The service deliberately returns only fact subjects during lookup. Values
    stay behind ``memory.read`` so an agent cannot accidentally dump a whole
    project's rules while resolving an abbreviation.
    """

    def __init__(self, repository: MemoryLookupRepository) -> None:
        self._repository = repository

    async def lookup(
        self,
        *,
        terms: Sequence[str],
        user_id: UUID,
        tenant_id: UUID,
        project_keys: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        requested_terms = _unique_terms(terms, limit=24)
        glossary_rows = await self._repository.list_visible_glossary(
            user_id=user_id, tenant_id=tenant_id, limit=MAX_GLOSSARY_ROWS,
        )
        glossary_matches, expanded_terms = self._match_glossary(requested_terms, glossary_rows)

        projects = await self._repository.list_active_projects(limit=MAX_PROJECT_ROWS)
        selected_projects, ambiguous_projects, suggestions = self._match_projects(
            projects=projects,
            expanded_terms=expanded_terms,
            requested_project_keys=project_keys or (),
        )
        facts = await self._repository.list_project_facts(
            tenant_id=tenant_id,
            project_ids=[project.id for project in selected_projects],
            limit=MAX_PROJECTS * MAX_KEYS_PER_PROJECT * 4,
        )
        keys_by_project = self._match_memory_keys(
            facts=facts, expanded_terms=expanded_terms,
        )
        return {
            "glossary": glossary_matches,
            "expanded_terms": expanded_terms[:48],
            "projects": [
                {
                    "project_key": project.key,
                    "name": project.name,
                    "keys": keys_by_project.get(project.id, []),
                }
                for project in selected_projects
            ],
            "ambiguous_projects": ambiguous_projects,
            "project_suggestions": suggestions,
        }

    async def read(
        self,
        *,
        tenant_id: UUID,
        projects: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for request in projects[:MAX_PROJECTS]:
            project_key = str(request.get("project_key") or "").strip().lower()
            keys = _unique_terms(request.get("keys") or (), limit=MAX_KEYS_PER_PROJECT)
            if not project_key or not keys:
                continue
            project, facts = await self._repository.read_project_facts(
                tenant_id=tenant_id,
                project_key=project_key,
                keys=keys,
                limit=MAX_KEYS_PER_PROJECT,
            )
            results.append({
                "project_key": project_key,
                "name": project.name if project is not None else None,
                "status": "ok" if project is not None else "project_unavailable",
                "entries": [self._fact_projection(fact) for fact in facts],
                "missing_keys": [key for key in keys if key not in {fact.subject for fact in facts}],
            })
        return {"projects": results}

    def _match_glossary(self, terms: Sequence[str], rows: Sequence[Any]) -> tuple[list[dict[str, Any]], list[str]]:
        matches: list[dict[str, Any]] = []
        expanded: list[str] = list(terms)
        for term in terms:
            query = normalize_memory_term(term)
            exact = [row for row in rows if query in {
                normalize_memory_term(row.canonical_term),
                *(normalize_memory_term(alias) for alias in row.aliases or []),
            }]
            for row in exact[:4]:
                forms = _unique_terms([row.canonical_term, *(row.aliases or [])], limit=20)
                expanded.extend(forms)
                matches.append({
                    "query": term,
                    "term": row.canonical_term,
                    "aliases": forms[1:],
                    "description": row.description or row.canonical_term,
                    "match": "exact",
                })
        return matches, _unique_terms(expanded, limit=48)

    def _match_projects(
        self,
        *,
        projects: Sequence[Project],
        expanded_terms: Sequence[str],
        requested_project_keys: Sequence[str],
    ) -> tuple[list[Project], list[dict[str, Any]], list[dict[str, Any]]]:
        forms = {normalize_memory_term(item) for item in expanded_terms}
        requested = {normalize_memory_term(item) for item in requested_project_keys if normalize_memory_term(item)}
        direct: list[Project] = []
        candidates: list[tuple[Project, list[str]]] = []
        for project in projects:
            matching = sorted(_matching_forms(project) & (requested or forms))
            if matching:
                candidates.append((project, matching))
        if requested:
            # Explicit keys constrain lookup; a missing key is not silently substituted.
            selected = [project for project, _ in candidates[:MAX_PROJECTS]]
            return selected, [], []
        owners: dict[str, set[str]] = defaultdict(set)
        for project, matching in candidates:
            for match in matching:
                owners[match].add(project.key)
        for project, matching in candidates:
            if any(len(owners[match]) == 1 for match in matching):
                direct.append(project)
        selected_keys = {project.key for project in direct}
        ambiguous = [
            {"project_key": project.key, "name": project.name, "matched_via": matching}
            for project, matching in candidates
            if project.key not in selected_keys
        ]
        return direct[:MAX_PROJECTS], ambiguous[:MAX_PROJECTS], self._project_suggestions(projects, forms) if not direct else []

    def _project_suggestions(self, projects: Sequence[Project], forms: set[str]) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        for project in projects:
            score = max(
                (SequenceMatcher(a=form, b=candidate).ratio() for form in forms for candidate in _matching_forms(project)),
                default=0.0,
            )
            if score >= 0.86:
                suggestions.append({"project_key": project.key, "name": project.name, "score": round(score, 2)})
        return sorted(suggestions, key=lambda item: item["score"], reverse=True)[:4]

    def _match_memory_keys(self, *, facts: Sequence[Fact], expanded_terms: Sequence[str]) -> dict[UUID, list[dict[str, Any]]]:
        terms = [normalize_memory_term(item) for item in expanded_terms if len(normalize_memory_term(item)) >= 2]
        matched: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        seen: set[tuple[UUID, str]] = set()
        for fact in facts:
            subject = normalize_memory_term(fact.subject)
            matched_via = [term for term in terms if term in subject]
            key = (fact.project_id, fact.subject)
            if not matched_via or fact.project_id is None or key in seen:
                continue
            seen.add(key)
            if len(matched[fact.project_id]) < MAX_KEYS_PER_PROJECT:
                matched[fact.project_id].append({
                    "key": fact.subject,
                    "label": fact.subject.replace("_", " ").replace(".", " "),
                    "kind": fact.kind or "fact",
                    "matched_via": matched_via[:4],
                })
        return matched

    @staticmethod
    def _fact_projection(fact: Fact) -> dict[str, Any]:
        return {
            "key": fact.subject,
            "value": fact.value,
            "kind": fact.kind or "fact",
            "confidence": fact.confidence,
        }
