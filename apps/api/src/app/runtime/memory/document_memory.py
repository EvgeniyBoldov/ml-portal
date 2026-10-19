"""Owner-local document passages. Accumulation is lossless and needs no LLM."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any


DOCUMENT_MEMORY_TYPES = {"document_memory", "planner_memory_result", "memory_recall"}


def passage_identity(item: dict[str, Any]) -> str:
    """Exact content and provenance identity, independent of retrieval score."""
    metadata = item.get("metadata") or {}
    refs = item.get("source_references") or metadata.get("source_refs") or []
    sources = sorted({json.dumps(ref, ensure_ascii=False, sort_keys=True)
                      for ref in refs if isinstance(ref, dict)})
    payload = [item.get("text", ""), sources, metadata.get("source_id"), metadata.get("document_id"),
               metadata.get("section_id"), metadata.get("chunk_id")]
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _result(entry: dict[str, Any]) -> dict[str, Any]:
    value = entry.get("result", entry)
    return value if isinstance(value, dict) and isinstance(value.get("groups"), list) else {}


def document_memory(context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only this owner's accumulated document-memory entry."""
    accumulated: list[dict[str, Any]] = []
    for entry in context:
        if entry.get("type") in DOCUMENT_MEMORY_TYPES and _result(entry):
            accumulated = accumulate_document_memory(accumulated, _result(entry))
    return accumulated


def accumulate_document_memory(context: list[dict[str, Any]], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Union exact passages within each scope; preserve text and source metadata.

    Failed/empty searches cannot erase earlier findings. Latest search status is
    retained per scope; complete individual responses remain in tool events.
    """
    core = [deepcopy(entry) for entry in context if entry.get("type") not in DOCUMENT_MEMORY_TYPES]
    groups: dict[str, dict[str, Any]] = {}
    for source in [*[_result(entry) for entry in context if entry.get("type") in DOCUMENT_MEMORY_TYPES], result]:
        for incoming in source.get("groups", []):
            scope = incoming["scope_slug"]
            previous = groups.get(scope, {})
            items = deepcopy(previous.get("items", []))
            seen = {passage_identity(item) for item in items}
            for item in incoming.get("items", []):
                identity = passage_identity(item)
                if identity not in seen:
                    items.append(deepcopy(item))
                    seen.add(identity)
            references = deepcopy(previous.get("source_references", []))
            for ref in incoming.get("source_references", []):
                if ref not in references:
                    references.append(deepcopy(ref))
            groups[scope] = {**deepcopy(incoming), "items": items, "count": len(items),
                             "source_references": references}
    if not groups:
        return core
    return [*core, {"type": "document_memory", "backend": "hipporag", "groups": list(groups.values()),
                   "group_count": len(groups), "partial": any(not group.get("success", True) for group in groups.values())}]


def search_receipt(record: dict[str, Any]) -> dict[str, Any]:
    """Keep search history without serializing passage text a second time."""
    result = record.get("result") or {}
    return {"tool": record.get("tool", "memory.search"), "arguments": record.get("arguments", {}),
            "success": result.get("success", True), "error_code": result.get("error_code"),
            "error": result.get("error"),
            "groups": [{key: group[key] for key in ("scope_slug", "status", "success", "count", "error_code", "error")
                        if key in group} for group in result.get("groups", [])]}
