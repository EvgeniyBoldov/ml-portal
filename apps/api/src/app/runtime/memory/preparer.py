"""Pre-planner selection of durable memory and project terminology."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Awaitable, Callable, Literal, Sequence
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
    memory_indexes: list[int] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    # Missing intent must never silently downgrade a potentially risky request.
    intent: Literal["informational", "action", "unknown"] = "unknown"
    # `durable` means the answer depends on company/project knowledge.  It
    # lets Recall distinguish a harmless general request from a memory miss
    # that must be grounded in RAG.
    knowledge_need: Literal["none", "durable", "current"] = "durable"


@dataclass(frozen=True)
class PreparedMemoryContext:
    items: list[dict[str, Any]]
    selected_fact_count: int
    selected_project_count: int
    selected_project_fact_count: int
    selected_glossary_count: int
    ambiguities: list[str]
    resolved_terms: list[str]
    resolved_projects: list[str]
    needs_source_check: bool
    source_check_reasons: list[str]
    intent: str = "unknown"
    knowledge_need: str = "durable"
    tool_required: bool = False
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
        project_facts: Sequence[dict[str, Any]] = (),
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
                    "aliases": item["aliases"],
                }
                for index, item in enumerate(glossary)
            ],
            # These are already ACL-filtered retrieval candidates.  Their
            # order carries hybrid retrieval rank, so the selector may retain
            # a semantic hit even where request wording has no lexical overlap.
            "semantic_memory": [
                {"index": index, "kind": item.get("kind"), "subject": item.get("subject"),
                 "value": str(item.get("value") or "")[:2000], "project_key": item.get("project_key"),
                 "state": item.get("state"), "confidence": item.get("confidence")}
                for index, item in enumerate(project_facts[:48])
            ],
        }
        fallback_intent = _conservative_intent(request_text, "unknown")
        fallback_tool_required = fallback_intent == "action" or _requires_current_observation(request_text)
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
            return PreparedMemoryContext(
                items=[],
                selected_fact_count=0,
                selected_project_count=0,
                selected_project_fact_count=0,
                selected_glossary_count=0,
                ambiguities=[],
                resolved_terms=[],
                resolved_projects=[],
                needs_source_check=True,
                source_check_reasons=[
                    "memory_preparation_failed",
                    *( ["current_state_required"] if fallback_tool_required else [] ),
                    *( [f"intent_{fallback_intent}"] if fallback_intent != "informational" else [] ),
                ],
                intent=fallback_intent,
                knowledge_need="current" if fallback_tool_required else "durable",
                tool_required=fallback_tool_required,
                fallback=True,
            )

        output = result.value
        # The selector is model-driven, so enforce a deterministic relevance
        # guard before personal facts can enter planner and sub-agent prompts.
        chosen_facts = [
            item for item in _by_indexes(facts, output.fact_indexes)
            if item.scope.value != "user" or _fact_matches_request(item, request_text)
        ]
        chosen_projects = _by_indexes(
            project_glossary,
            _merge_indexes(
                output.project_indexes,
                _exact_match_indexes(request_text, project_glossary, ("key", "name", "aliases")),
            ),
        )
        chosen_glossary = _by_indexes(
            glossary,
            _merge_indexes(
                output.glossary_indexes,
                _exact_match_indexes(request_text, glossary, ("term", "aliases")),
            ),
        )
        # The indexes refer exactly to ``semantic_memory`` in the payload.
        # Do not filter first (which changes indexes), and never inject an
        # arbitrary "top four" candidate when the selector chose none.
        matched_project_facts = _by_indexes(project_facts, output.memory_indexes)[:12]
        selected_project_facts = [
            item for item in matched_project_facts
            if str(item.get("state") or "active") == "active"
        ]
        items = [
            {"type": "fact", "scope": item.scope.value, "subject": item.subject, "value": item.value}
            for item in chosen_facts
        ] + [
            {"type": "project", "project_id": str(item["id"]), "key": item["key"], "name": item["name"], "matched_aliases": item["aliases"]}
            for item in chosen_projects
        ] + [
            {
                "type": "company_knowledge" if item.get("project_id") is None else "project_knowledge",
                "scope": "company" if item.get("project_id") is None else "project",
                "project_id": str(item.get("project_id")) if item.get("project_id") is not None else None,
                "project_key": item.get("project_key"),
                "kind": item.get("kind") or "knowledge",
                "subject": item.get("subject"),
                "value": item.get("value"),
                "content": dict(item.get("content") or {}),
                "confidence": item.get("confidence"),
                "source_ref": item.get("source_ref"),
                "memory_item_id": item.get("memory_item_id"),
                "selected_claim_id": item.get("selected_claim_id"),
                "source_references": list(item.get("source_references") or []),
                "claim_ids": list(item.get("claim_ids") or []),
                "observed_at": item.get("observed_at"),
            }
            for item in selected_project_facts
        ] + [
            {
                "type": "glossary",
                "term": item["term"],
                "aliases": item["aliases"],
            }
            for item in chosen_glossary
        ]
        ambiguities = [item[:240] for item in output.ambiguities[:4] if item.strip()]
        source_check_reasons: list[str] = []
        knowledge_need = output.knowledge_need
        if knowledge_need == "durable" and not selected_project_facts and not chosen_facts:
            source_check_reasons.append("semantic_memory_missing")
        elif chosen_projects and not selected_project_facts:
            source_check_reasons.append("semantic_memory_missing")
        if any(str(item.get("state") or "active") == "uncertain" for item in matched_project_facts):
            source_check_reasons.append("semantic_memory_uncertain")
        intent = _conservative_intent(request_text, output.intent)
        # Executing an action is handled by the normal planner/tool contract.
        # Recall requires an additional *read* observation only when the user
        # asks about current state.  Neither case automatically means RAG.
        tool_required = _requires_current_observation(request_text)
        return PreparedMemoryContext(
            items=items,
            selected_fact_count=len(chosen_facts),
            selected_project_count=len(chosen_projects),
            selected_project_fact_count=len(selected_project_facts),
            selected_glossary_count=len(chosen_glossary),
            ambiguities=ambiguities,
            resolved_terms=[
                str(item.get("term"))
                for item in chosen_glossary
                if isinstance(item, dict) and str(item.get("term") or "").strip()
            ],
            resolved_projects=[
                str(item.get("key"))
                for item in chosen_projects
                if isinstance(item, dict) and str(item.get("key") or "").strip()
            ],
            needs_source_check=bool(source_check_reasons),
            source_check_reasons=source_check_reasons,
            intent=intent,
            knowledge_need=knowledge_need,
            tool_required=tool_required or knowledge_need == "current",
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


def _merge_indexes(*groups: Sequence[int]) -> list[int]:
    merged: list[int] = []
    seen: set[int] = set()
    for group in groups:
        for index in group:
            if isinstance(index, int) and index not in seen:
                seen.add(index)
                merged.append(index)
    return merged


def _exact_match_indexes(
    request_text: str,
    candidates: Sequence[dict[str, Any]],
    fields: Sequence[str],
) -> list[int]:
    """Guarantee exact company terminology/project matches survive LLM selection."""
    query = _normalize_term(request_text)
    if not query:
        return []
    indexes: list[int] = []
    for index, candidate in enumerate(candidates):
        forms: list[str] = []
        for field in fields:
            value = candidate.get(field)
            if isinstance(value, (list, tuple)):
                forms.extend(str(item) for item in value)
            elif value is not None:
                forms.append(str(value))
        if any(_term_matches_query(_normalize_term(form), query) for form in forms):
            indexes.append(index)
    return indexes


def _term_matches_query(term: str, query: str) -> bool:
    # Short company abbreviations are only accepted as an exact token; they
    # must never enter fuzzy matching but also must not disappear between
    # glossary resolution and the model-driven selector.
    if term and term in _tokens(query):
        return True
    if len(term) < 3:
        return False
    if term in query:
        return True
    if " " in term:
        return False
    return any(
        len(token) >= 4 and SequenceMatcher(a=term, b=token).ratio() >= 0.8
        for token in _tokens(query)
    )


_ACTION_INTENT_RE = re.compile(
    r"\b(измен(?:и|ить|яем|ение)|настро(?:й|ить|йка)|удал(?:и|ить|ение)|"
    r"созда(?:й|ть|ние)|включ(?:и|ить)|выключ(?:и|ить)|примен(?:и|ить)|"
    r"deploy|change|configure|delete|create|enable|disable|apply)\b",
    re.IGNORECASE,
)

_HOW_TO_RE = re.compile(
    r"\b(как|порядок|инструкци\w*|процедур\w*|шаг\w*|что\s+нужн\w*|"
    r"how\s+(?:to|do)|procedure|instructions?)\b",
    re.IGNORECASE,
)

_CURRENT_OBSERVATION_RE = re.compile(
    r"\b(сейчас|текущ\w*|актуальн\w*|статус\w*|состояни\w*|"
    r"установлен\w*|работает|запущен\w*|current|status|state|running)\b",
    re.IGNORECASE,
)


def _requires_current_observation(request_text: str) -> bool:
    """Memory documents describe policy, not the live state of a system."""
    return bool(_CURRENT_OBSERVATION_RE.search(str(request_text or "")))


def _conservative_intent(request_text: str, model_intent: str) -> str:
    """Never let an omitted/stale role contract downgrade an action to info."""
    # Describing a change is not executing it.  This check intentionally
    # precedes the imperative/action detector: "как изменить VLAN" must be
    # answered from a procedure and must not require a live write-capable tool.
    if _HOW_TO_RE.search(str(request_text or "")):
        return "informational"
    if _ACTION_INTENT_RE.search(str(request_text or "")):
        return "action"
    return model_intent if model_intent in {"informational", "action", "unknown"} else "unknown"


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


def _normalize_term(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())
