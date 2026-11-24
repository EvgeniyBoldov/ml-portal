"""Validate primary material before handing a model draft to the Synthesizer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.runtime.run_context import RunContext
from app.runtime.turn_preflight import DirectAnswerBrief


_FILE_READS = {"file.read", "file.data.read", "file.data.search"}
_MEMORY_ONLY = re.compile(
    r"\bтолько\s+(?:(?:по|в|из)\s+)?(?:документн\w*\s+)?памят\w*\b"
    r"|\bonly\s+(?:(?:from|in|using)\s+)?(?:document\s+)?memory\b",
    re.IGNORECASE,
)
_CORPORATE_TERMS = re.compile(
    r"\b(?:внутрикорпоративн\w*|наш[а-яё]*\s+(?:компани|организаци)\w*|"
    r"our\s+(?:company|organi[sz]ation)|company[- ]specific)\b",
    re.IGNORECASE,
)


@dataclass
class DirectGrounding:
    run_context: dict[str, Any]
    facts: list[dict[str, Any]]
    invalid_refs: set[str] = field(default_factory=set)
    memory_search_status: list[dict[str, Any]] = field(default_factory=list)
    answer_draft: str | None = None
    failure: str | None = None


def _has_text(items: Any) -> bool:
    return any(str(item.get("text") or "").strip() for item in items or [] if isinstance(item, dict))


def _memory_groups(result: dict[str, Any], scope_keys: list[str]) -> list[dict[str, Any]]:
    groups = result.get("groups")
    if isinstance(groups, list):
        return [group for group in groups if group.get("scope_slug") in scope_keys]
    return [result] if isinstance(result.get("items"), list) else []


def _has_evidence(item: dict[str, Any], scope_keys: list[str]) -> bool:
    data = item["data"]
    if not data.get("success", True):
        return False
    if item["tool"] == "memory.search":
        return any(group.get("success", True) and _has_text(group.get("items"))
                   for group in _memory_groups(data, scope_keys))
    if item["tool"] in {"file.read", "file.data.read"}:
        return bool(str(data.get("content") or "").strip()) and data.get("representation") != "binary"
    if item["tool"] == "file.data.search":
        return _has_text(data.get("hits"))
    return False


def validate_direct_grounding(
    brief: DirectAnswerBrief,
    *,
    user_request: str,
    run_context: RunContext,
    scope_keys: list[str],
    facts_context: list[dict[str, Any]],
    artifact_ids: set[str],
    fresh_evidence_ids: set[str],
    tool_results: list[dict[str, Any]],
    mechanical_lookup: dict[str, Any],
    runtime_answer: bool = False,
) -> DirectGrounding:
    synthesis = brief.synthesis_brief
    context = run_context.projection(
        scope_keys=scope_keys, evidence_refs=synthesis.evidence_refs, message_refs=synthesis.message_refs,
    )
    known_facts = {
        str(item["id"]): item for item in facts_context
        if item.get("id") and item.get("scope") in {"user", "tenant"} and item.get("kind") == "fact"
        and str(item.get("value") or "").strip()
    }
    fact_refs = list(dict.fromkeys([*brief.fact_refs, *synthesis.fact_refs]))
    facts = [
        {key: value for key, value in known_facts[ref].items()
         if key in {"id", "scope", "kind", "subject", "value", "confidence"}}
        for ref in fact_refs if ref in known_facts
    ]
    stale_files = {
        item["id"] for item in context["evidence"]
        if item["tool"] in _FILE_READS and item["id"] not in fresh_evidence_ids
    }
    invalid = (set(context.get("unavailable_material_refs") or []) | stale_files
               | (set(fact_refs) - known_facts.keys()) | (set(synthesis.artifact_refs) - artifact_ids))
    outcome = DirectGrounding(run_context=context, facts=facts, invalid_refs=invalid)
    request_excerpt = (brief.request_excerpt or "").strip()
    memory_only = brief.grounding == "memory_only" or bool(_MEMORY_ONLY.search(user_request))
    if invalid or (brief.request_excerpt is not None and (not request_excerpt or request_excerpt not in user_request)):
        outcome.failure = "Выбранные материалы не подтверждены или недоступны. Проверь источники и ответь на исходный запрос."
        if memory_only:
            outcome.failure += " Для поиска фактов используй только документную память."
        return outcome

    if runtime_answer:
        return outcome

    if memory_only:
        if (facts or request_excerpt or context["conversation_materials"]
                or any(item["tool"] != "memory.search" for item in context["evidence"])):
            outcome.failure = "Используй только документную память для поиска фактов и сообщи результат поиска."
            return outcome
        searches = [record["result"] for record in tool_results if record.get("tool") == "memory.search"]
        if not searches:
            outcome.failure = "Выполни запрошенный поиск только в документной памяти и сообщи его результат."
            return outcome
        groups = [group for search in searches if search.get("success")
                  for group in _memory_groups(search, scope_keys)]
        outcome.memory_search_status = [
            {
                "scope_slug": group.get("scope_slug"),
                "success": group.get("success", True),
                "count": len(group.get("items") or []),
            }
            for group in groups
        ] + [{"success": False} for search in searches if not search.get("success")]
        successful = [group for group in groups if group.get("success", True)]
        if not any(_has_text(group.get("items")) for group in successful):
            failed = any(not status["success"] for status in outcome.memory_search_status)
            if successful and failed:
                outcome.answer_draft = "В проверенной части памяти подходящих сведений нет. Часть поиска завершилась ошибкой."
            elif successful:
                outcome.answer_draft = "Поиск в документной памяти не вернул подходящих сведений."
            elif failed:
                outcome.answer_draft = "Не удалось получить результаты поиска в документной памяти."
            else:
                outcome.answer_draft = "Поиск не охватил ни одной области документной памяти."
                outcome.memory_search_status.append({"status": "no_scopes"})
        elif not any(
            item["tool"] == "memory.search" and _has_evidence(item, scope_keys) for item in context["evidence"]
        ):
            outcome.failure = "Используй только документную память. Выбери найденные фрагменты для ответа или уточни запрос к памяти."
        return outcome

    messages = context["conversation_materials"]
    primary_material = bool(facts) or any(_has_evidence(item, scope_keys) for item in context["evidence"])
    delivering_existing_file = synthesis.delivery == "files" and bool(synthesis.artifact_refs) and not synthesis.files
    if brief.grounding == "supplied_material":
        if not (primary_material or request_excerpt or any(item.get("content") for item in messages) or delivering_existing_file):
            outcome.failure = "Получить материал, который пользователь просит обработать, и продолжить работу по нему."
        return outcome

    corporate = synthesis.content_mode != "generative" and (
        _CORPORATE_TERMS.search(user_request) or mechanical_lookup.get("projects") or mechanical_lookup.get("glossary")
    )
    if brief.grounding == "corporate" or corporate or (
        brief.grounding is None and synthesis.content_mode != "generative" and not delivering_existing_file
    ):
        if not primary_material:
            outcome.failure = "Для прямого ответа не получены подтверждающие материалы. Проверь подходящие источники для исходного запроса."
    return outcome
