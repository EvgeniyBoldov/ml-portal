"""Bounded model-facing projections for retained runtime evidence."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from typing import Any

from app.adapters.impl.llm_context import estimate_request_tokens, INPUT_SAFETY_FACTOR, MIN_OUTPUT_FRACTION
from app.services.runtime_limits_service import RuntimeLimitsService
from sqlalchemy.ext.asyncio import AsyncSession


def _tokens(value: Any, model: str = "") -> int:
    return estimate_request_tokens({"model": model, "messages": [{"role": "user", "content": json.dumps(
        value, ensure_ascii=False, default=str, separators=(",", ":"))}]})


async def prompt_payload_budget(*, session: Any, model: str, system_prompt: str, schema: Any) -> int | None:
    """Estimate payload allowance after the real deployment, prompt and schema."""
    if not isinstance(session, AsyncSession):
        return None
    try:
        limits = await RuntimeLimitsService(session).resolve_model(model or None)
    except AttributeError:
        # Lightweight unit fakes may not provide a database session. Production
        # calls have an AsyncSession and are bounded before StructuredLLMCall.
        return None
    base = {"model": model, "messages": [{"role": "system", "content": system_prompt},
                                         {"role": "user", "content": "{}"}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": getattr(schema, "__name__", "response"),
                "schema": schema.model_json_schema(), "strict": True}}}
    total = estimate_request_tokens(base)
    output_reserve = math.ceil(limits.context_window_tokens * MIN_OUTPUT_FRACTION)
    # The JSON payload replaces `{}` in the placeholder request. Subtracting
    # fixed prompt/schema cost yields a model-aware input allowance.
    placeholder = estimate_request_tokens({"model": model, "messages": [{"role": "user", "content": "{}"}]})
    return max(0, limits.context_window_tokens - output_reserve - math.ceil(total * INPUT_SAFETY_FACTOR) + placeholder)


def bound_prompt_memory(payload: dict[str, Any], *, token_budget: int, model: str) -> dict[str, Any]:
    """Apply one shared token allowance to memory and selected read evidence."""
    result = deepcopy(payload)
    read_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    locations: list[tuple[dict[str, Any], str, list[Any]]] = []
    for record in result.get("memory_tool_results", []) if isinstance(result.get("memory_tool_results"), list) else []:
        value = record.get("result") if isinstance(record, dict) else None
        if isinstance(value, dict) and isinstance(value.get("groups"), list):
            locations.append((value, "groups", value["groups"]))
        elif (isinstance(record, dict) and record.get("tool") in {
                "file.read", "file.data.read", "file.data.search", "chat.history.read"}
              and isinstance(value, dict)):
            read_records.append((record, deepcopy(value)))
            record["result"] = {key: value[key] for key in (
                "success", "error_code", "error", "artifact_id", "representation_id",
                "offset", "next_offset", "has_more", "truncated", "total_chars", "count",
            ) if key in value}
    for entry in result.get("memory_context", []) if isinstance(result.get("memory_context"), list) else []:
        if not isinstance(entry, dict):
            continue
        target = entry.get("result") if entry.get("type") == "planner_memory_result" else entry
        if isinstance(target, dict) and isinstance(target.get("groups"), list):
            locations.append((target, "groups", target["groups"]))
    omitted: list[str] = []
    run_context = result.get("run_context")
    saved_evidence: list[dict[str, Any]] = []
    saved_messages: list[dict[str, Any]] = []
    if isinstance(run_context, dict):
        saved_evidence = [item for item in run_context.get("evidence", []) if isinstance(item, dict)]
        saved_messages = [item for item in run_context.get("conversation_materials", []) if isinstance(item, dict)]
        run_context["evidence"] = []
        run_context["conversation_materials"] = []
    originals = [(target, key, deepcopy(groups)) for target, key, groups in locations]
    for target, key, groups in locations:
        target[key] = [{**group, "items": []} if isinstance(group, dict) else group for group in groups]
    if _tokens(result, model) > token_budget:
        return {**result, "evidence_coverage": "unavailable",
                "limitation": "Непаспортная часть prompt уже превышает выделенный бюджет модели."}
    from app.runtime.memory.document_memory import passage_identity
    for (target, key, _), (_, _, groups) in zip(locations, originals):
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            for item in group.get("items", []) if isinstance(group.get("items"), list) else []:
                target[key][group_index].setdefault("items", []).append(deepcopy(item))
                if _tokens(result, model) > token_budget:
                    target[key][group_index]["items"].pop()
                    if isinstance(item, dict):
                        omitted.append(passage_identity(item))
    omitted_materials: list[str] = []
    omitted_reads: list[str] = []
    for record, original_result in read_records:
        record["result"] = original_result
        if _tokens(result, model) > token_budget:
            record["result"] = {key: original_result[key] for key in (
                "success", "error_code", "error", "artifact_id", "representation_id",
                "offset", "next_offset", "has_more", "truncated", "total_chars", "count",
            ) if key in original_result}
            omitted_reads.append(str(record.get("evidence_id") or record.get("tool") or "read-result"))
    if isinstance(run_context, dict):
        for item in saved_evidence:
            run_context["evidence"].append(item)
            if _tokens(result, model) > token_budget:
                run_context["evidence"].pop()
                omitted_materials.append(str(item.get("id") or ""))
        for item in saved_messages:
            run_context["conversation_materials"].append(item)
            if _tokens(result, model) > token_budget:
                run_context["conversation_materials"].pop()
                omitted_materials.append(str(item.get("message_id") or ""))
        if omitted_materials:
            run_context["omitted_material_refs"] = omitted_materials
            by_id = {str(item.get("id")): item for item in saved_evidence}
            by_message = {str(message.get("message_id")): message for message in saved_messages}
            recovery: list[dict[str, Any]] = []
            for ref in omitted_materials:
                source = by_id.get(ref)
                if source is not None:
                    recovery.append({"id": ref, "tool": source.get("tool"),
                                     "arguments": source.get("arguments") or {},
                                     "recoverability": "available" if source.get("tool") in {
                                         "file.read", "file.data.read", "file.data.search", "chat.history.read"}
                                     else "not_exact"})
                elif ref in by_message:
                    history = next((item for item in saved_evidence if item.get("tool") == "chat.history.read"), None)
                    recovery.append({"id": ref, "tool": "chat.history.read",
                        "arguments": history.get("arguments") if history else {},
                        "recoverability": "best_effort"})
            if recovery:
                run_context["omitted_material_recovery"] = recovery
            run_context["evidence_coverage"] = "partial"
            run_context["limitation"] = "Некоторые выбранные file/history материалы не помещены в бюджет; исходные записи сохранены в RunContext."
    if omitted:
        result["omitted_passage_ids"] = omitted[:16]
        result["omitted_passage_count"] = len(omitted)
        result["memory_evidence_coverage"] = "partial"
        result["memory_limitation"] = "Часть memory passages опущена из prompt; точное восстановление через memory.search не гарантируется."
    elif not omitted_materials:
        result["evidence_coverage"] = "complete"
    if omitted_reads:
        result["omitted_read_refs"] = omitted_reads[:16]
        result["omitted_read_count"] = len(omitted_reads)
        result["evidence_coverage"] = "partial"
    if _tokens(result, model) > token_budget:
        return {**result, "evidence_coverage": "unavailable",
                "limitation": "Prompt projection metadata exceeds the model input allowance; outbound allocator will fail safely if needed."}
    return result


def bounded_grouped_memory(value: dict[str, Any], *, token_budget: int, model: str = "") -> dict[str, Any]:
    """Project grouped passages within one token budget; the input remains lossless.

    Omitted passage IDs are stable content identities; the full evidence remains
    in RunContext for downstream preparation. Memory search cannot replay exact
    passages, so this projection never asks the model to repeat a search.
    """
    result = deepcopy(value)
    groups = result.get("groups")
    if not isinstance(groups, list):
        return result
    original = deepcopy(groups)
    projected = deepcopy(groups)
    omitted: list[str] = []
    # Start with metadata and then add complete passages in source order. Never
    # truncate passage text or provenance; a passage either fits or is omitted.
    for group in projected:
        if isinstance(group, dict):
            group["items"] = []
    result["groups"] = projected
    for group_index, group in enumerate(original):
        if not isinstance(group, dict):
            continue
        for item in group.get("items", []) if isinstance(group.get("items"), list) else []:
            candidate = deepcopy(item)
            projected[group_index].setdefault("items", []).append(candidate)
            if _tokens(result, model) > token_budget:
                projected[group_index]["items"].pop()
                from app.runtime.memory.document_memory import passage_identity
                if isinstance(item, dict):
                    omitted.append(passage_identity(item))
    result["groups"] = projected
    if _tokens(result, model) > token_budget:
        # Keep only useful status/provenance keys when retrieval metadata itself
        # exceeds the budget; passage text is never partially clipped.
        result["groups"] = [{key: group[key] for key in (
            "scope_slug", "status", "success", "count", "error_code", "error"
        ) if key in group} for group in projected if isinstance(group, dict)]
    result["omitted_passage_ids"] = omitted[:32]
    if len(omitted) > 32:
        result["omitted_passage_count"] = len(omitted)
    result["evidence_coverage"] = "partial" if omitted else "complete"
    if omitted:
        result["limitation"] = "Часть passage опущена из prompt; точное восстановление через memory.search не гарантируется."
    if _tokens(result, model) > token_budget:
        return {"evidence_coverage": "unavailable", "omitted_passage_count": len(omitted),
                "limitation": "Результат поиска не помещается в выделенный бюджет контекста."}
    return result


def evidence_catalog(evidence: list[Any]) -> list[dict[str, str]]:
    """Small index for selected and omitted evidence, without copying payloads."""
    return [{"id": item.id, "tool": item.tool, "status": "available"} for item in evidence]
