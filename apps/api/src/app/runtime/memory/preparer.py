"""Pre-planner selection of durable memory and project terminology."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Awaitable, Callable, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.memory.dto import FactDTO


class _PreparationOutput(BaseModel):
    fact_indexes: list[int] = Field(default_factory=list)
    project_indexes: list[int] = Field(default_factory=list)
    glossary_indexes: list[int] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PreparedMemoryContext:
    items: list[dict[str, Any]]
    selected_fact_count: int
    selected_project_count: int
    selected_glossary_count: int
    ambiguities: list[str]
    fallback: bool = False


class MemoryPreparer:
    """One bounded LLM call that prepares Planner's memory input."""

    def __init__(self, *, session: AsyncSession, llm_client: LLMClientProtocol) -> None:
        self._structured = StructuredLLMCall(session=session, llm_client=llm_client)

    async def prepare(
        self,
        *,
        request_text: str,
        facts: Sequence[FactDTO],
        project_glossary: Sequence[dict[str, Any]],
        glossary: Sequence[dict[str, Any]],
        user_id: UUID | None,
        tenant_id: UUID | None,
        chat_id: UUID | None,
        sandbox_overrides: dict[str, Any] | None,
        event_sink: Callable[[RuntimeEvent], Awaitable[None]] | None = None,
        agent_execution_id: str | None = None,
    ) -> PreparedMemoryContext:
        payload = {
            "request": request_text,
            "facts": [
                {"index": index, "scope": item.scope.value, "subject": item.subject, "value": item.value}
                for index, item in enumerate(facts)
            ],
            "projects": [
                {"index": index, "id": str(item["id"]), "key": item["key"], "name": item["name"], "aliases": item["aliases"]}
                for index, item in enumerate(project_glossary)
            ],
            "glossary": [
                {
                    "index": index,
                    "term": item["term"],
                    "description": item["description"],
                    "aliases": item["aliases"],
                }
                for index, item in enumerate(glossary)
            ],
        }
        try:
            result = await self._structured.invoke(
                role=SystemLLMRoleType.MEMORY,
                payload=payload,
                schema=_PreparationOutput,
                user_id=user_id,
                tenant_id=tenant_id,
                chat_id=chat_id,
                sandbox_overrides=sandbox_overrides,
                event_sink=event_sink,
                agent_execution_id=agent_execution_id,
            )
        except Exception:  # memory preparation is optional
            return PreparedMemoryContext(items=[], selected_fact_count=0, selected_project_count=0, selected_glossary_count=0, ambiguities=[], fallback=True)

        output = result.value
        # The selector is model-driven, so enforce a deterministic relevance
        # guard before personal facts can enter planner and sub-agent prompts.
        chosen_facts = [
            item for item in _by_indexes(facts, output.fact_indexes)
            if item.scope.value != "user" or _fact_matches_request(item, request_text)
        ]
        chosen_projects = _by_indexes(project_glossary, output.project_indexes)
        chosen_glossary = _by_indexes(glossary, output.glossary_indexes)
        items = [
            {"type": "fact", "scope": item.scope.value, "subject": item.subject, "value": item.value}
            for item in chosen_facts
        ] + [
            {"type": "project", "project_id": str(item["id"]), "key": item["key"], "name": item["name"], "matched_aliases": item["aliases"]}
            for item in chosen_projects
        ] + [
            {
                "type": "glossary",
                "scope": "global",
                "term": item["term"],
                "description": item["description"],
                "aliases": item["aliases"],
            }
            for item in chosen_glossary
        ]
        return PreparedMemoryContext(
            items=items,
            selected_fact_count=len(chosen_facts),
            selected_project_count=len(chosen_projects),
            selected_glossary_count=len(chosen_glossary),
            ambiguities=[item[:240] for item in output.ambiguities[:4] if item.strip()],
        )


def _by_indexes(items: Sequence[Any], indexes: Sequence[int]) -> list[Any]:
    selected: list[Any] = []
    seen: set[int] = set()
    for index in indexes:
        if not isinstance(index, int) or index in seen or index < 0 or index >= len(items):
            continue
        seen.add(index)
        selected.append(items[index])
    return selected


_PERSONAL_SUBJECT_ALIASES = {
    "имя": {"имя", "зовут", "фамил"},
    "возраст": {"возраст", "лет", "год"},
    "есть дети": {"дет", "ребен"},
    "хобби": {"хобби", "увлеч", "теннис", "чтен"},
    "user.hobby": {"хобби", "увлеч", "теннис", "чтен"},
    "должность": {"должност", "работ", "роль", "професс"},
    "user.role": {"должност", "работ", "роль", "професс"},
    "user.jira.username": {"мо", "мне", "меня", "назнач", "assignee", "jira"},
}


def _fact_matches_request(fact: FactDTO, request_text: str) -> bool:
    """Require direct lexical or known-intent relevance for personal memory."""
    query = _tokens(request_text)
    if not query:
        return False
    subject = str(fact.subject or "").strip().lower()
    fact_tokens = _tokens(f"{fact.subject} {fact.value}")
    if query & fact_tokens:
        return True
    aliases = _PERSONAL_SUBJECT_ALIASES.get(subject, set())
    return any(any(token.startswith(alias) for token in query) for alias in aliases)


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[\wа-яА-ЯёЁ]{2,}", str(value or ""))
    }
