"""Bounded model projection of the full runtime transcript."""
from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable
from app.runtime.memory.tool_ledger import canonical_operation_name


_RESULT_READER_ARGUMENT_KEYS = (
    "result_id", "revision", "query", "q", "columns", "selection_id", "view", "path", "offset", "limit", "fields",
    "text_offset", "text_limit", "child_offset", "child_limit",
    "input_result_id", "input_revision", "query_complete", "page_may_have_more", "schema_offset",
)
_RESULT_OBSERVATION_KEYS = (
    "result_id", "revision", "q", "columns", "offset", "limit", "fields", "read_complete", "next_offset",
    "source_complete", "source_total", "query_complete", "input_result_id", "input_revision",
    "page_may_have_more", "path", "text_offset", "text_limit", "next_text_offset",
    "child_offset", "child_limit", "next_child_offset", "recovery_reason", "delivery",
    "row_count", "view",
)
_COMPACT_SUMMARY_ITEMS = 8
_COMPACT_SUMMARY_TEXT_CHARS = 320


def _bounded_distinct_summary(value: Any, *, plain_text_items: bool = False) -> dict[str, Any] | None:
    """Retain bounded redacted MCP text while accounting for omitted material.

    Only MCP text blocks are eligible. Resource, file and binary bodies are
    deliberately excluded from the prompt compaction receipt.
    """
    from app.runtime.redactor import RuntimeRedactor

    blocks = value if isinstance(value, list) else [value]
    if (not plain_text_items and isinstance(value, dict) and isinstance(value.get("items"), list)
            and any(key in value for key in ("original_count", "omitted_count", "warning_summaries"))):
        return _compact_normalized_mcp_content(value)

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    omitted_items = 0
    duplicate_items = 0
    omitted_chars = 0
    text_chars = 0
    for block in blocks:
        if plain_text_items and isinstance(block, str):
            raw_text = block
        elif plain_text_items and isinstance(block, dict):
            warning_parts = [str(block[key]) for key in ("code", "warning", "message", "detail")
                             if isinstance(block.get(key), str)]
            raw_text = ": ".join(warning_parts) if warning_parts else None
        elif isinstance(block, dict) and str(block.get("type") or "").lower() == "text":
            raw_text = block.get("text")
        else:
            omitted_items += 1
            omitted_chars += len(json.dumps(block, ensure_ascii=False, default=str))
            continue
        if not isinstance(raw_text, str):
            omitted_items += 1
            continue
        safe_text = str(RuntimeRedactor().redact(raw_text))
        if safe_text in seen:
            omitted_items += 1
            duplicate_items += 1
            omitted_chars += len(safe_text)
            continue
        seen.add(safe_text)
        text_chars += len(safe_text)
        if len(items) >= _COMPACT_SUMMARY_ITEMS:
            omitted_items += 1
            omitted_chars += len(safe_text)
            continue
        excerpt = safe_text[:_COMPACT_SUMMARY_TEXT_CHARS]
        omitted_chars += max(0, len(safe_text) - len(excerpt))
        items.append({"type": "text", "text": excerpt,
                      "excerpt_complete": len(safe_text) <= _COMPACT_SUMMARY_TEXT_CHARS})
    if not items and omitted_items == 0:
        return None
    return {
        "items": items,
        "coverage": {
            "included_items": len(items),
            "omitted_items": omitted_items,
            "duplicate_items": duplicate_items,
            "omitted_text_chars": omitted_chars,
            "observed_text_chars": text_chars,
            "complete": omitted_items == 0 and omitted_chars == 0,
        },
    }


def _compact_normalized_mcp_content(value: dict[str, Any]) -> dict[str, Any]:
    """Compact the production `_meaningful_mcp_content` envelope and its counters."""
    summary = _bounded_distinct_summary(value.get("items", [])) or {
        "items": [], "coverage": {"included_items": 0, "omitted_items": 0,
            "duplicate_items": 0, "omitted_text_chars": 0, "observed_text_chars": 0,
            "complete": True},
    }
    source_omitted = value.get("omitted_count")
    source_omitted = source_omitted if isinstance(source_omitted, int) and source_omitted >= 0 else 0
    source_duplicates = value.get("duplicate_count")
    source_duplicates = source_duplicates if isinstance(source_duplicates, int) and source_duplicates >= 0 else 0
    summary_coverage = summary["coverage"]
    summary_omitted = summary_coverage["omitted_items"]
    summary_duplicates = summary_coverage.get("duplicate_items", 0)
    omitted_count = source_omitted + max(0, summary_omitted - summary_duplicates)

    warning_summary = _bounded_distinct_summary(
        value.get("warning_summaries", []), plain_text_items=True
    ) or {"items": [], "coverage": {"included_items": 0, "omitted_items": 0,
        "duplicate_items": 0, "omitted_text_chars": 0, "observed_text_chars": 0,
        "complete": True}}
    source_warnings_omitted = value.get("warnings_omitted")
    source_warnings_omitted = (source_warnings_omitted if isinstance(source_warnings_omitted, int)
                               and source_warnings_omitted >= 0 else 0)
    warnings_omitted = source_warnings_omitted + warning_summary["coverage"]["omitted_items"]
    upstream_truncated = value.get("truncated") is True
    complete = (summary_coverage["complete"] and warning_summary["coverage"]["complete"]
                and not upstream_truncated and source_omitted == 0 and source_warnings_omitted == 0)
    original_count = value.get("original_count")
    return {
        "items": summary["items"],
        "original_count": original_count if isinstance(original_count, int) and original_count >= 0 else None,
        "omitted_count": omitted_count,
        "duplicate_count": source_duplicates + summary_duplicates,
        "truncated": upstream_truncated or omitted_count > 0 or summary_coverage["omitted_text_chars"] > 0,
        "warning_summaries": [item["text"] for item in warning_summary["items"]],
        "warnings_omitted": warnings_omitted,
        "coverage": {
            **summary_coverage,
            "upstream_omitted_count": source_omitted,
            "upstream_truncated": upstream_truncated,
            "complete": complete,
        },
        "warning_summary_coverage": warning_summary["coverage"],
    }


def _bounded_identity_value(value: Any) -> tuple[Any, int] | None:
    """Keep an entire safe reader identity value or omit it with a count."""
    from app.runtime.redactor import RuntimeRedactor

    redactor = RuntimeRedactor()
    if isinstance(value, str):
        if len(value) > 512 or redactor.redact(value) != value:
            return None
        return value, 0
    if isinstance(value, list):
        if len(value) > 16:
            return None
        if any(not (isinstance(item, (str, int, float, bool)) or item is None) for item in value):
            return None
        if any(isinstance(item, str) and
               (len(item) > 512 or redactor.redact(item) != item) for item in value):
            return None
        return value, 0
    if isinstance(value, (int, float, bool)) or value is None:
        return value, 0
    return None


def _bounded_next_action(value: Any) -> dict[str, Any] | None:
    """Retain only a supported result reader action and bounded reader args."""
    if not isinstance(value, dict):
        return None
    tool = value.get("tool")
    if tool not in {"result.read", "result.describe", "result.aggregate", "result.find"}:
        return None
    arguments = value.get("arguments")
    if not isinstance(arguments, dict):
        return None
    allowed = {
        "result.read": {"result_id", "revision", "offset", "limit", "fields", "path", "text_offset",
                        "text_limit", "child_offset", "child_limit", "view"},
        "result.describe": {"result_id", "offset", "limit", "query", "schema_offset"},
        "result.aggregate": {"result_id", "revision", "offset", "limit", "columns"},
        "result.find": {"result_id", "revision", "offset", "limit", "q", "columns"},
    }[tool]
    bounded = _current_result_observation({}, {key: item for key, item in arguments.items() if key in allowed})
    result = {"tool": tool, "arguments": bounded["reader_arguments"] if bounded else {}}
    omitted_keys = set((bounded or {}).get("arguments_omission", {}).get("omitted_keys", []))
    unknown_keys = set(arguments) - allowed
    omitted_keys.update(str(key) for key in unknown_keys)
    if omitted_keys:
        result["arguments_omission"] = {
            "omitted_values": len(omitted_keys),
            "omitted_keys": sorted(omitted_keys),
            "complete": False,
        }
    required = {
        "result.read": ("result_id", "offset", "limit"),
        "result.describe": ("result_id",),
        "result.aggregate": ("result_id", "revision", "offset", "limit", "columns"),
        "result.find": ("result_id", "revision", "offset", "limit", "q"),
    }[tool]
    if any(key not in result["arguments"] for key in required):
        return None
    if tool == "result.find" and (not isinstance(result["arguments"].get("q"), str)
                                   or not result["arguments"]["q"].strip()):
        return None
    if tool == "result.aggregate" and (not isinstance(result["arguments"].get("columns"), list)
                                        or not result["arguments"]["columns"]):
        return None
    if tool in {"result.find", "result.aggregate"} and (
        not isinstance(result["arguments"].get("revision"), int)
        or isinstance(result["arguments"].get("revision"), bool)
        or result["arguments"]["revision"] < 1
    ):
        return None
    if tool in {"result.find", "result.aggregate"}:
        page_offset = result["arguments"].get("offset")
        page_limit = result["arguments"].get("limit")
        if (not isinstance(page_offset, int) or isinstance(page_offset, bool) or page_offset < 0
                or not isinstance(page_limit, int) or isinstance(page_limit, bool)
                or not 1 <= page_limit <= 100):
            return None
    return result


def _fallback_action_from_current(operation: str | None, current: dict[str, Any] | None) -> dict[str, Any] | None:
    """Use supported current reader arguments when required identity is intact."""
    if not operation or not isinstance(current, dict):
        return None
    tool = canonical_operation_name(operation)
    if tool not in {"result.read", "result.describe", "result.aggregate", "result.find"}:
        return None
    arguments = current.get("reader_arguments")
    if not isinstance(arguments, dict):
        return None
    required = {
        "result.read": ("result_id", "offset", "limit"),
        "result.describe": ("result_id",),
        "result.aggregate": ("result_id", "revision", "offset", "limit", "columns"),
        "result.find": ("result_id", "revision", "offset", "limit", "q"),
    }[tool]
    if any(key not in arguments for key in required):
        return None
    # The current receipt separately records any dropped optional or unknown
    # values. Do not copy those raw values back into an executable action.
    return _bounded_next_action({"tool": tool, "arguments": arguments})


def _current_result_observation(value: dict[str, Any], reader_arguments: Any = None) -> dict[str, Any] | None:
    """Keep current read identity independently of any future next_action."""
    args = reader_arguments if isinstance(reader_arguments, dict) else {}
    observation = value.get("result_observation")
    if not isinstance(observation, dict):
        runtime = value.get("_runtime_result")
        observation = runtime.get("result_observation") if isinstance(runtime, dict) else None
    observation = observation if isinstance(observation, dict) else {}
    current_args: dict[str, Any] = {}
    omitted_fields = 0
    omitted_keys: list[str] = []
    omitted_keys.extend(str(key) for key in set(args) - set(_RESULT_READER_ARGUMENT_KEYS))
    omitted_fields += len(set(args) - set(_RESULT_READER_ARGUMENT_KEYS))
    for key in _RESULT_READER_ARGUMENT_KEYS:
        if key not in args:
            continue
        item = args[key]
        bounded = _bounded_identity_value(item)
        if bounded is None:
            omitted_fields += 1
            omitted_keys.append(key)
        else:
            current_args[key] = bounded[0]
    current_observation: dict[str, Any] = {}
    for key in _RESULT_OBSERVATION_KEYS:
        if key not in observation:
            continue
        item = observation[key]
        bounded = _bounded_identity_value(item)
        if bounded is None:
            omitted_fields += 1
            omitted_keys.append(key)
        else:
            current_observation[key] = bounded[0]
    # Native workspace replies echo the actual current read arguments at root.
    for key in _RESULT_READER_ARGUMENT_KEYS:
        if key not in current_args and key in value:
            item = value[key]
            bounded = _bounded_identity_value(item)
            if bounded is None:
                omitted_fields += 1
                omitted_keys.append(key)
            else:
                current_args[key] = bounded[0]
    if not current_args and not current_observation and not omitted_fields:
        return None
    result = {"reader_arguments": current_args, "result_observation": current_observation}
    if omitted_fields:
        result["arguments_omission"] = {
            "omitted_values": omitted_fields, "omitted_keys": sorted(set(omitted_keys)), "complete": False,
        }
    return result


def _compact_recoverable_result(
    value: dict[str, Any], *, reader_arguments: Any = None, operation: str | None = None,
) -> dict[str, Any]:
    """Build a compact receipt, retaining the exact page already observed."""
    compact = {key: value[key] for key in (
        "status", "result_id", "revision", "source_coverage", "source_complete", "source_total",
        "query_complete", "page_may_have_more", "read_complete", "snapshot_only", "imported_from",
        "recoverability", "reason", "recovery_reason", "omitted_ids", "coverage", "view",
    ) if key in value}
    current = _current_result_observation(value, reader_arguments)
    if current:
        compact["current_result"] = current
    action = value.get("next_action")
    bounded_action = _bounded_next_action(action) if action is not None else None
    if bounded_action is None:
        bounded_action = _fallback_action_from_current(operation, current)
    if bounded_action is not None:
        compact["next_action"] = bounded_action
    for key in ("mcp_content", "warnings", "warning"):
        if key in value:
            summary = _bounded_distinct_summary(value[key], plain_text_items=key != "mcp_content")
            if summary is not None:
                compact[key] = summary
    runtime = value.get("_runtime_result")
    if isinstance(runtime, dict):
        metadata = {key: runtime[key] for key in (
            "result_id", "operation", "payload_type", "row_count", "inline_complete", "source_complete",
            "revision", "source_total", "snapshot_only", "imported_from", "delivery", "view",
        ) if key in runtime}
        for key in ("mcp_content", "warnings", "warning"):
            if key in runtime:
                summary = _bounded_distinct_summary(runtime[key], plain_text_items=key != "mcp_content")
                if summary is not None and summary != compact.get(key):
                    metadata[key] = summary
        compact["_runtime_result"] = metadata
    return compact


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
    call_arguments: dict[str, Any] = {}
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
                raw_arguments = function.get("arguments")
                if isinstance(raw_arguments, str):
                    try:
                        raw_arguments = json.loads(raw_arguments)
                    except (TypeError, ValueError):
                        raw_arguments = None
                call_arguments[str(call["id"])] = raw_arguments
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
        reader_arguments = call_arguments.get(str(message.get("tool_call_id") or ""))
        # Keep the latest read facts in full; compact older tool payloads into a
        # pointer with any runtime receipt metadata retained.
        try:
            value = json.loads(content)
        except (TypeError, ValueError):
            value = None
        if isinstance(value, dict) and isinstance(value.get("_runtime_result"), dict):
            metadata = value["_runtime_result"]
            # A result id is the proof that the omitted payload is recoverable.
            # Preserve ordinary direct evidence even if it resembles metadata.
            if not metadata.get("result_id"):
                continue
            compact = _compact_recoverable_result(value, reader_arguments=reader_arguments, operation=operation)
            compact["_runtime_result"] = _compact_recoverable_result(
                {"_runtime_result": metadata}, reader_arguments=reader_arguments, operation=operation
            ).get("_runtime_result", {})
            compact["receipt"] = "Earlier result retained in the runtime result store; inspect it again if needed."
            message["content"] = json.dumps(compact, ensure_ascii=False)
        elif (isinstance(value, dict) and value.get("status") in {"ready", "already_completed"}
              and isinstance(value.get("result_id"), str) and value.get("result_id")
              and canonical_operation_name(operation).split(".", 1)[0] == "result"):
            compact = _compact_recoverable_result(value, reader_arguments=reader_arguments, operation=operation)
            compact["receipt"] = "Earlier saved result; inspect it again if needed."
            message["content"] = json.dumps(compact, ensure_ascii=False)
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
        nested_input = deepcopy(nested_value)
        if (isinstance(nested_input, dict) and "result_observation" not in nested_input
                and isinstance(value.get("result_observation"), dict)):
            nested_input["result_observation"] = value["result_observation"]
        receipt["result"] = _compact_recoverable_result(
            nested_input, reader_arguments=value.get("arguments"), operation=tool_name
        )
        for key in ("mcp_content", "warnings", "warning"):
            if key in value:
                summary = _bounded_distinct_summary(value[key], plain_text_items=key != "mcp_content")
                if summary is not None:
                    receipt[key] = summary
        metadata = value.get("_runtime_result")
        if isinstance(metadata, dict):
            receipt["_runtime_result"] = _compact_recoverable_result(
                {"_runtime_result": metadata}, reader_arguments=value.get("arguments"), operation=tool_name
            ).get("_runtime_result", {})
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
