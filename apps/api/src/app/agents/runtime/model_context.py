"""Bounded model projection of the full runtime transcript."""
from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable
from app.runtime.memory.tool_ledger import canonical_operation_name


@dataclass(frozen=True)
class BatchContextBudget:
    model: str | None
    context_window_tokens: int
    result_tokens: int


@dataclass(frozen=True)
class BatchResultAllocation:
    """Final model-visible result strings and their exact request-fit status."""

    texts: list[str]
    used_tokens: int
    remaining_tokens: int
    fits_request: bool
    full_candidate_selected: list[bool]
    omitted_call_ids: list[str]


def reallocate_result_batch(
    items: list[dict[str, Any]], *, total_budget_tokens: int, model: str | None,
    format_item: Callable[[dict[str, Any], int], str],
    request_for_texts: Callable[[list[str]], dict[str, Any]], context_window_tokens: int,
) -> BatchResultAllocation:
    """Allocate result space batch-wide, then validate the exact outbound body.

    Every operation's minimum receipt is measured before upgrades. Full outputs
    that fit as a set are delivered independent of call order; otherwise smaller
    upgrades are selected deterministically. If exact full-request estimation
    rejects an upgrade, all results retreat to minimum receipts together.
    """
    from app.adapters.impl.llm_context import estimate_request_tokens, inspect_context

    def token_count(text: str) -> int:
        return estimate_request_tokens({"model": model, "messages": [{"role": "tool", "content": text}]})

    minimum_texts = [str(item.get("minimum_receipt")) if item.get("minimum_receipt") is not None
                     else format_item(item, 0) for item in items]
    minimum_tokens = [token_count(text) for text in minimum_texts]
    full_texts = [format_item(item, total_budget_tokens) for item in items]
    full_tokens = [token_count(text) for text in full_texts]
    minimum_total = sum(minimum_tokens)
    if minimum_total > total_budget_tokens:
        return BatchResultAllocation(minimum_texts, minimum_total,
            total_budget_tokens - minimum_total, False, [False] * len(items),
            [str(item.get("call_id") or "") for item in items])

    chosen = list(minimum_texts)
    chosen_tokens = list(minimum_tokens)
    remaining = total_budget_tokens - minimum_total
    upgrades = sorted(range(len(items)), key=lambda index: (full_tokens[index] - minimum_tokens[index], index))
    for index in upgrades:
        cost = full_tokens[index] - minimum_tokens[index]
        if cost <= remaining:
            chosen[index] = full_texts[index]
            chosen_tokens[index] = full_tokens[index]
            remaining -= cost
    # Spend leftover space on bounded intermediate views where a full result
    # did not fit; order by incremental full cost and stable call identity.
    partial_candidates = [index for index, content in enumerate(chosen)
                          if content == minimum_texts[index] and full_texts[index] != minimum_texts[index]]
    partial_candidates.sort(key=lambda index: (full_tokens[index] - minimum_tokens[index],
                                                str(items[index].get("call_id") or "")))
    for position, index in enumerate(partial_candidates):
        if remaining <= 0:
            break
        share = remaining // max(1, len(partial_candidates) - position)
        candidate = format_item(items[index], minimum_tokens[index] + share)
        candidate_tokens = token_count(candidate)
        if minimum_tokens[index] < candidate_tokens <= minimum_tokens[index] + share:
            chosen[index] = candidate
            chosen_tokens[index] = candidate_tokens
            remaining -= candidate_tokens - minimum_tokens[index]
    used = sum(chosen_tokens)

    def request_fits(texts: list[str]) -> bool:
        try:
            request = request_for_texts(texts)
            allocation = inspect_context(request, context_window_tokens)
            return allocation.max_output_tokens >= allocation.minimum_output_tokens
        except Exception:
            return False

    fits = request_fits(chosen)
    if not fits:
        chosen = minimum_texts
        chosen_tokens = minimum_tokens
        used = minimum_total
        remaining = total_budget_tokens - used
        fits = request_fits(chosen)
    selected_full = [chosen[index] == full_texts[index] for index in range(len(items))]
    omitted = [str(items[index].get("call_id") or "") for index, complete in enumerate(selected_full) if not complete]
    return BatchResultAllocation(chosen, used, remaining, fits, selected_full, omitted)


def outbound_request_snapshot(
    *, model: str | None, messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None, tool_choice: str | None = None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical request body used by provider, trace and token estimator."""
    snapshot: dict[str, Any] = {"model": model, "messages": deepcopy(messages)}
    if tools is not None:
        snapshot["tools"] = deepcopy(tools)
        snapshot["tool_choice"] = tool_choice or "auto"
    if response_format is not None:
        snapshot["response_format"] = deepcopy(response_format)
    return snapshot


def project_model_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact older result bodies while preserving native call/result pairing.

    The durable/checkpoint transcript remains untouched. The latest result batch
    stays verbatim so fresh evidence and read facts remain available to the model.
    """
    projected = deepcopy(messages)
    latest_assistant_call = max(
        (i for i, message in enumerate(projected)
         if message.get("role") == "assistant" and message.get("tool_calls")),
        default=-1,
    )
    call_names: dict[str, str] = {}
    latest_text_result_index = max((i for i, message in enumerate(projected)
                                    if message.get("role") == "user"
                                    and isinstance(message.get("content"), str)
                                    and "```tool_result" in message["content"]), default=-1)
    for message in projected:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            if call.get("id"):
                call_names[str(call["id"])] = str(function.get("name") or "")
    for index, message in enumerate(projected):
        if message.get("role") == "user":
            content = message.get("content")
            if (index < latest_text_result_index and isinstance(content, str)
                    and "```tool_result" in content):
                message["content"] = _compact_text_tool_results(content)
            continue
        if message.get("role") != "tool" or index >= latest_assistant_call:
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        operation = call_names.get(str(message.get("tool_call_id") or ""), "")
        # Keep the latest read facts in full; compact older tool payloads into a
        # pointer with any runtime receipt metadata retained.
        try:
            import json
            value = json.loads(content)
        except (TypeError, ValueError):
            value = None
        if isinstance(value, dict) and isinstance(value.get("_runtime_result"), dict):
            metadata = value["_runtime_result"]
            # A result id is the proof that the omitted payload is recoverable.
            # Preserve ordinary direct evidence even if it resembles metadata.
            if not metadata.get("result_id"):
                continue
            message["content"] = json.dumps({
                "_runtime_result": {key: metadata.get(key) for key in (
                    "result_id", "operation", "payload_type", "row_count", "inline_complete",
                    "source_complete", "revision", "result_observation", "next_action", "offset", "limit",
                    "fields", "path", "text_offset", "text_limit", "child_offset", "child_limit",
                    "next_offset", "read_complete", "query_complete", "input_result_id", "input_revision",
                    "page_may_have_more", "recovery_reason", "delivery", "source_total",
                    "snapshot_only", "imported_from",
                    "view",
                ) if key in metadata},
                "receipt": "Earlier result retained in the runtime result store; inspect it again if needed.",
            }, ensure_ascii=False)
        elif (isinstance(value, dict) and value.get("status") in {"ready", "already_completed"}
              and isinstance(value.get("result_id"), str) and value.get("result_id")
              and canonical_operation_name(operation).split(".", 1)[0] == "result"):
            message["content"] = json.dumps({
                "status": value["status"],
                "result_id": value["result_id"],
                "revision": value.get("revision", 1),
                "source_coverage": value.get("source_coverage"),
                "snapshot_only": value.get("snapshot_only"),
                "imported_from": value.get("imported_from"),
                "view": value.get("view"),
                "next_action": value.get("next_action") or {
                    "tool": "result.read",
                    "arguments": {"result_id": value["result_id"], "revision": value.get("revision", 1),
                                  **{key: value[key] for key in ("offset", "limit", "fields", "path",
                                      "text_offset", "text_limit", "child_offset", "child_limit", "view") if key in value}},
                    "message": "Read the saved records if needed.",
                },
                "receipt": "Earlier saved result; inspect it again if needed.",
            }, ensure_ascii=False)
    return projected


def _compact_text_tool_results(content: str) -> str:
    """Bound older textual tool-result blocks without hiding their status."""
    import re

    pattern = re.compile(r"(?s)(```tool_result\s*)(\{.*?\})(\s*```)" )

    def compact(match: re.Match[str]) -> str:
        try:
            value = json.loads(match.group(2))
        except (TypeError, ValueError):
            return match.group(0)
        if not isinstance(value, dict):
            return match.group(0)
        nested = value.get("result")
        if isinstance(nested, str):
            try:
                nested_value = json.loads(nested)
            except (TypeError, ValueError):
                nested_value = None
        else:
            nested_value = nested
        tool_name = str(value.get("tool") or "")
        canonical_tool = canonical_operation_name(tool_name).split(".", 1)[0]
        recoverable_envelope = isinstance(nested_value, dict) and isinstance(nested_value.get("_runtime_result"), dict)
        if (not isinstance(nested_value, dict) or not nested_value.get("result_id")
                or (canonical_tool != "result" and not recoverable_envelope)):
            # Direct and unrecoverable evidence must remain available.
            return match.group(0)
        receipt: dict[str, Any] = {}
        for key in ("tool", "operation", "success", "status", "error_code", "evidence_call_id",
                    "result_id", "revision", "recoverability", "omitted_ids", "coverage"):
            if key in value:
                receipt[key] = value[key]
        for key in ("status", "result_id", "revision", "source_coverage", "next_action",
                    "read_complete", "page_may_have_more", "query_complete", "omitted_ids",
                    "snapshot_only", "imported_from", "view"):
            if key in nested_value:
                receipt[key] = nested_value[key]
        metadata = value.get("_runtime_result")
        if isinstance(metadata, dict):
            receipt["_runtime_result"] = {key: metadata[key] for key in (
                "result_id", "revision", "inline_complete", "source_complete") if key in metadata}
        if not receipt:
            return match.group(0)
        receipt["receipt"] = "Earlier tool result body omitted from model context; identifiers and explicit omissions retained."
        return match.group(1) + json.dumps(receipt, ensure_ascii=False) + match.group(3)

    return pattern.sub(compact, content)


def bound_document_memory_request(
    request: dict[str, Any], *, context_window_tokens: int, reserve_output_tokens: int = 1024,
) -> dict[str, Any]:
    """Trim passage projection until the exact next request fits its input budget.

    The full owner-local memory stays in runtime state. The request gets explicit
    coverage and omitted passage identities, never fabricated replacement text.
    """
    from app.adapters.impl.llm_context import inspect_context

    projected = deepcopy(request)
    messages = projected.get("messages") or []
    target = next((message for message in messages if isinstance(message.get("content"), str)
                   and message["content"].startswith("[Document memory for this task]")), None)
    if target is None:
        return projected
    content = target["content"]
    decoder = json.JSONDecoder()
    memory = None
    suffix_start = -1
    # Production prompts have a prose preamble, followed by the serialized
    # document_memory list. Find the trailing JSON object/array without assuming
    # that it starts immediately after the heading.
    for position in (i + 1 for i, char in enumerate(content) if char == "\n"):
        try:
            value, end = decoder.raw_decode(content, position)
        except (ValueError, TypeError):
            continue
        if content[end:].strip() == "" and isinstance(value, (dict, list)):
            memory, suffix_start = value, position
            break
    if memory is None:
        return projected
    prompt_prefix = content[:suffix_start]
    containers = memory if isinstance(memory, list) else [memory]
    groups: list[dict[str, Any]] = []
    for container in containers:
        if isinstance(container, dict) and isinstance(container.get("groups"), list):
            groups.extend(group for group in container["groups"] if isinstance(group, dict))
    if not groups:
        return projected
    omitted: list[str] = []

    def identity(item: dict[str, Any], group_index: int, item_index: int) -> str:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        for key in ("passage_id", "chunk_id", "section_id", "document_id", "artifact_id", "source_id"):
            value = item.get(key) or metadata.get(key)
            if value:
                return str(value)
        return hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    def render() -> None:
        projection = {"included_passages": sum(len(group.get("items") or []) for group in groups),
                      "omitted_passage_count": len(omitted), "omitted_passage_ids": omitted}
        for container in containers:
            if isinstance(container, dict) and isinstance(container.get("groups"), list):
                container["projection_coverage"] = projection
        target["content"] = prompt_prefix + "\n" + json.dumps(memory, ensure_ascii=False, default=str)

    render()
    def fits() -> bool:
        try:
            allocation = inspect_context(projected, context_window_tokens)
            return allocation.max_output_tokens >= max(
                allocation.minimum_output_tokens, reserve_output_tokens)
        except Exception:
            return False

    while not fits():
        candidates = [(group_index, item_index, item) for group_index, group in enumerate(groups)
                      for item_index, item in enumerate(group.get("items") or [])]
        if not candidates:
            break
        # Keep the newest passage from every scope when possible; evict oldest
        # remaining passages first, preserving source IDs for explicit coverage.
        group_index, item_index, item = candidates[0]
        group = groups[group_index]
        omitted.append(identity(item, group_index, item_index))
        group["items"].pop(item_index)
        render()
    # If even metadata exceeds budget, omit passages from the wire and retain a
    # compact coverage receipt. No passage is synthesized.
    if not fits():
        for container in containers:
            if not isinstance(container, dict) or not isinstance(container.get("groups"), list):
                continue
            compact_groups = []
            for group_index, group in enumerate(container["groups"]):
                if not isinstance(group, dict):
                    continue
                compact_group = {key: group[key] for key in ("scope_slug", "status", "success", "count") if key in group}
                for item_index, item in enumerate(group.get("items") or []):
                    passage_id = identity(item, group_index, item_index)
                    if passage_id not in omitted:
                        omitted.append(passage_id)
                compact_group["items"] = []
                compact_groups.append(compact_group)
            container["groups"] = compact_groups
        # Drop preamble prose only when even the metadata receipt plus the
        # actual request's tool/schema overhead misses the required reserve.
        prompt_prefix = "[Document memory for this task]"
        render()
    if not fits():
        compact_memory = [{"type": "document_memory", "projection_coverage": {
            "included_passages": 0, "omitted_passage_count": len(omitted),
            "omitted_passage_ids": omitted,
        }}]
        target["content"] = prompt_prefix + "\n" + json.dumps(compact_memory, ensure_ascii=False)
    return projected


def runtime_result_metadata(content: str) -> dict[str, Any]:
    """Extract the runtime-owned receipt envelope from model-visible content."""
    try:
        import json
        value = json.loads(content)
    except (TypeError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    metadata = value.get("_runtime_result")
    if isinstance(metadata, dict):
        return metadata
    # Current model receipt; the older envelope above remains readable on resume.
    if value.get("status") in {"ready", "already_completed"} and value.get("result_id"):
        coverage = value.get("source_coverage")
        return {
            "result_id": value["result_id"],
            "revision": value.get("revision", 1),
            "inline_complete": "records" in value,
            "source_complete": coverage.get("complete") if isinstance(coverage, dict) else None,
            "snapshot_only": value.get("snapshot_only"),
            "imported_from": value.get("imported_from"),
        }
    return {}


def model_result_inline_complete(content: str, *, stored_result: dict[str, Any] | None,
                                result_success: bool, direct_truncated: bool = False) -> bool:
    """Read the final model-visible completeness from formatted result content."""
    metadata = runtime_result_metadata(content)
    if "inline_complete" in metadata:
        return bool(metadata["inline_complete"])
    try:
        presented = json.loads(content)
    except (TypeError, ValueError):
        presented = None
    if stored_result:
        return bool(isinstance(presented, dict) and "records" in presented
                    and not presented.get("record_too_large"))
    return bool(result_success and isinstance(presented, dict)
                and presented.get("status") != "unavailable" and not direct_truncated)


def update_result_inline_coverage(ledger: Any, *, call_id: str, inline_complete: bool) -> None:
    """Synchronize final presentation metadata without adding a tool result."""
    update = getattr(ledger, "update_result_presentation", None)
    if callable(update):
        update(call_id=call_id, inline_complete=inline_complete)


def observe_no_progress_batch(
    state: dict[str, Any], calls: list[Any], outputs: list[dict[str, Any]], *, threshold: int,
) -> tuple[bool, bool]:
    """Track consecutive identical reused/blocked batches for one execution."""
    blocked_codes = {"duplicate_execution_blocked"}
    no_progress = bool(outputs) and all(
        bool(item.get("reused"))
        or (not bool(item.get("success")) and str(item.get("error_code") or "") in blocked_codes)
        for item in outputs
    )
    if not no_progress:
        state.pop("runtime_no_progress_signature", None)
        state.pop("runtime_no_progress_repeats", None)
        return False, False
    signature = json_signature([
        (getattr(call, "tool_name", ""), getattr(call, "arguments", {})) for call in calls
    ])
    previous = state.get("runtime_no_progress_signature")
    repeat_count = int(state.get("runtime_no_progress_repeats") or 0)
    repeat_count = repeat_count + 1 if previous == signature else 1
    state["runtime_no_progress_signature"] = signature
    state["runtime_no_progress_repeats"] = repeat_count
    return True, repeat_count >= threshold


def json_signature(value: Any) -> str:
    import json
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def project_datastore(datastore: dict[str, Any]) -> dict[str, Any]:
    """Keep the model inventory small; schema remains available via describe."""
    return {**datastore, "items": [
        {key: item[key] for key in (
            "kind", "result_id", "operation", "revision", "row_count", "source_complete",
        ) if key in item} if item.get("kind") == "result" else item
        for item in datastore.get("items", [])
    ]}
