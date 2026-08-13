"""Pre-planner selection of durable memory and project terminology."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.events import RuntimeEvent
from app.runtime.llm.structured import StructuredLLMCall
from app.runtime.memory.dto import FactDTO


MEMORY_PREPARATION_PROMPT = """Ты готовишь короткий контекст памяти для планера.
У тебя нет tools, ты не отвечаешь пользователю и не строишь план.
Выбери только факты user/tenant, прямо полезные для текущего запроса. Выбирай
проекты только если пользователь явно упомянул их название или alias. Не
добавляй project facts, правила проекта или новые знания. Верни JSON строго
по схеме; используй только индексы, полученные на входе."""


class _PreparationOutput(BaseModel):
    fact_indexes: list[int] = Field(default_factory=list)
    project_indexes: list[int] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PreparedMemoryContext:
    items: list[dict[str, Any]]
    selected_fact_count: int
    selected_project_count: int
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
        }
        try:
            result = await self._structured.invoke(
                role=SystemLLMRoleType.MEMORY,
                system_prompt=MEMORY_PREPARATION_PROMPT,
                payload=payload,
                schema=_PreparationOutput,
                user_id=user_id,
                tenant_id=tenant_id,
                chat_id=chat_id,
                sandbox_overrides=sandbox_overrides,
                event_sink=event_sink,
                agent_execution_id=agent_execution_id,
                fallback_factory=lambda _raw: _PreparationOutput(),
            )
        except Exception:  # memory preparation is optional
            return PreparedMemoryContext(items=[], selected_fact_count=0, selected_project_count=0, ambiguities=[], fallback=True)

        output = result.value
        chosen_facts = _by_indexes(facts, output.fact_indexes)
        chosen_projects = _by_indexes(project_glossary, output.project_indexes)
        items = [
            {"type": "fact", "scope": item.scope.value, "subject": item.subject, "value": item.value}
            for item in chosen_facts
        ] + [
            {"type": "project", "project_id": str(item["id"]), "key": item["key"], "name": item["name"], "matched_aliases": item["aliases"]}
            for item in chosen_projects
        ]
        return PreparedMemoryContext(
            items=items,
            selected_fact_count=len(chosen_facts),
            selected_project_count=len(chosen_projects),
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
