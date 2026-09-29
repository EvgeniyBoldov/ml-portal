"""Deterministic project-context resolution for one runtime turn."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.runtime.memory.dto import FactDTO
from app.services.project_catalog_service import ProjectCatalogService


PROJECT_SCOPE_SUBJECT = "user.project_scope"


@dataclass(frozen=True)
class ProjectContext:
    explicit_project_keys: tuple[str, ...] = ()
    chat_project_keys: tuple[str, ...] = ()
    default_project_keys: tuple[str, ...] = ()
    ambiguities: tuple[str, ...] = ()

    @property
    def effective_project_keys(self) -> tuple[str, ...]:
        return self.explicit_project_keys or self.chat_project_keys or self.default_project_keys

    @property
    def source(self) -> str:
        if self.explicit_project_keys:
            return "explicit"
        if self.chat_project_keys:
            return "chat_context"
        return "user_default" if self.default_project_keys else "none"

    def as_dict(self) -> dict[str, object]:
        return {
            "explicit_project_keys": list(self.explicit_project_keys),
            "chat_project_keys": list(self.chat_project_keys),
            "default_project_keys": list(self.default_project_keys),
            "effective_project_keys": list(self.effective_project_keys),
            "source": self.source,
            "ambiguous": bool(self.ambiguities),
            "ambiguities": list(self.ambiguities),
        }


class ProjectContextResolver:
    """Resolves project aliases mechanically; it deliberately has no LLM path."""

    def __init__(self, session) -> None:
        self._projects = ProjectCatalogService(session)

    async def resolve(
        self, *, request_text: str, facts: Iterable[FactDTO],
        chat_project_keys: Iterable[str] = (),
    ) -> ProjectContext:
        projects = await self._projects.list_projects()
        known = {str(item.get("key") or "").strip().casefold() for item in projects}
        defaults = _scope_keys(facts, known)
        chat_keys = list(dict.fromkeys(
            str(key).strip().casefold() for key in chat_project_keys
            if str(key).strip().casefold() in known
        ))
        matches: dict[str, set[str]] = {}
        for project in projects:
            key = str(project.get("key") or "").strip().casefold()
            for form in _forms(project):
                if form and _contains_form(request_text, form):
                    matches.setdefault(form, set()).add(key)
        explicit: set[str] = set()
        ambiguities: list[str] = []
        for form, keys in matches.items():
            if len(keys) == 1:
                explicit.update(keys)
            else:
                ambiguities.append(f"ambiguous_project_alias:{form}")
        return ProjectContext(
            explicit_project_keys=tuple(sorted(explicit)),
            chat_project_keys=tuple(chat_keys),
            default_project_keys=tuple(defaults),
            ambiguities=tuple(sorted(set(ambiguities))),
        )


def _scope_keys(facts: Iterable[FactDTO], known: set[str]) -> list[str]:
    for fact in facts:
        if fact.subject != PROJECT_SCOPE_SUBJECT:
            continue
        values = fact.metadata.get("project_keys") if isinstance(fact.metadata, dict) else None
        if not isinstance(values, list):
            continue
        keys = [str(value).strip().casefold() for value in values]
        return list(dict.fromkeys(key for key in keys if key in known))
    return []


def _forms(project: dict[str, object]) -> set[str]:
    values = {str(project.get("key") or "").strip().casefold(), str(project.get("name") or "").strip().casefold()}
    values.update(str(value).strip().casefold() for value in project.get("aliases") or [])
    return {value for value in values if value}


def _contains_form(text: str, form: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(form)}(?!\w)", text.casefold()))
