"""Bounded model projection of the full runtime transcript."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


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
        if index >= latest_assistant_call:
            continue
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        operation = call_names.get(str(message.get("tool_call_id") or ""), "")
        if operation.removeprefix("instance.") in {
            "result.read", "result.describe", "result.sql", "result.load",
            "result.aggregate", "result.find", "result.analyze", "memory.search",
        }:
            continue
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
                    "source_complete", "revision",
                ) if key in metadata},
                "receipt": "Earlier result retained in the runtime result store; inspect it again if needed.",
            }, ensure_ascii=False)
        elif (isinstance(value, dict) and value.get("status") in {"ready", "already_completed"}
              and isinstance(value.get("result_id"), str) and value.get("result_id")):
            message["content"] = json.dumps({
                "status": value["status"],
                "result_id": value["result_id"],
                "revision": value.get("revision", 1),
                "source_coverage": value.get("source_coverage"),
                "next_action": value.get("next_action") or {
                    "tool": "result.read",
                    "arguments": {"result_id": value["result_id"], "revision": value.get("revision", 1)},
                    "message": "Read the saved records if needed.",
                },
                "receipt": "Earlier saved result; inspect it again if needed.",
            }, ensure_ascii=False)
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
        }
    return {}


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
