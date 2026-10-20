"""Content-free file/dataset inventories for role-specific model inputs.

This is a prompt projection over existing stores, not a persistence surface or
an authorization mechanism. File and result tools still validate every access.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from app.runtime.redactor import RuntimeRedactor


logger = logging.getLogger(__name__)

def task_files(results: Iterable[Any]) -> list[dict[str, Any]]:
    """Collect explicit file deliveries and source passports, never scan payloads."""
    files: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        verified = result.get("verified") or {}
        for key, fallback in (("attachments", "artifacts"), ("sources", "sources")):
            files.extend(item for item in result.get(key) or verified.get(fallback) or []
                         if isinstance(item, dict) and item.get("artifact_id"))
    return files


def result_references(value: Any) -> set[str]:
    """Find explicit dataset references in task inputs/outputs, not arbitrary UUIDs."""
    refs: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("result_id"), str):
            refs.add(value["result_id"])
        for item in value.values():
            refs.update(result_references(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(result_references(item))
    return refs


def file_metadata(items: Iterable[Any]) -> list[dict[str, Any]]:
    """Normalize attachment contexts, delivery DTOs and canonical passports."""
    files: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref") if isinstance(item.get("ref"), dict) else item
        passport = item.get("artifact") if isinstance(item.get("artifact"), dict) else ref
        artifact_id = str(ref.get("artifact_id") or passport.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        file = passport.get("file") or {}
        description = passport.get("description") or ref.get("description")
        if isinstance(description, str):
            description = {"text": description[:600]}
        elif isinstance(description, dict) and isinstance(description.get("text"), str):
            description = {key: description[key] for key in ("text", "source", "representation_id")
                           if isinstance(description.get(key), str)}
            description["text"] = description["text"][:600]
        else:
            description = None
        representation = passport.get("representation") or {}
        entry = {
            "kind": "file", "artifact_id": artifact_id,
            "file_name": file.get("name") or ref.get("file_name") or ref.get("name") or "file",
            "content_type": file.get("media_type") or ref.get("content_type"),
            "size_bytes": file.get("size_bytes", ref.get("size_bytes")),
            "origin": {key: value for key, value in (passport.get("origin") or ref.get("origin") or {}).items()
                       if key in {"kind", "source_id", "source_type", "collection_id", "created_by_run_id"}
                       and isinstance(value, str)},
            "description": description,
            "is_current": bool(item.get("is_current")),
            "representation_id": representation.get("id") or item.get("representation_id"),
            "representation_status": representation.get("status") or item.get("representation_status") or item.get("snippet_status") or "unread",
            "source_complete": item.get("source_complete"),
            "data_indexes": {backend: {key: value for key, value in entry.items()
                             if key in {"status", "representation_id", "source_fingerprint", "chunk_count", "expires_at"}}
                for backend, entry in (ref.get("data_indexes") or (passport.get("attributes") or {}).get("file_data") or {}).items()
                if isinstance(entry, dict)},
        }
        # Later, richer passports may supplement an earlier attachment context.
        previous = files.get(artifact_id, {})
        if previous:
            if not (file.get("name") or ref.get("file_name") or ref.get("name")):
                entry["file_name"] = previous["file_name"]
            entry["is_current"] = previous.get("is_current", False) or entry["is_current"]
            if not representation and not item.get("representation_status") and not item.get("snippet_status"):
                entry["representation_status"] = previous.get("representation_status", "unread")
        files[artifact_id] = {**previous, **{key: value for key, value in entry.items()
                                          if value is not None and value != {}}}
    return list(files.values())


def build_datastore(*, files: Iterable[Any] = (), results: Iterable[Any] = (),
                    task_ids: set[str] | None = None, result_ids: set[str] | None = None,
                    deleted_artifact_ids: Iterable[str] = (),
                    results_status: str = "available") -> dict[str, Any]:
    """Project only the supplied files and selected dataset catalog entries."""
    from app.services.result_sql_projection import schema_page

    deleted = set(deleted_artifact_ids)
    items = [item for item in file_metadata(files) if item["artifact_id"] not in deleted]
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, dict) or not result.get("result_id"):
            continue
        result_id = str(result["result_id"])
        if task_ids is not None and str(result.get("task_id") or "") not in task_ids and result_id not in (result_ids or set()):
            continue
        if result_id in seen:
            continue
        seen.add(result_id)
        items.append({
            "kind": "result", "result_id": result_id,
            "operation": result.get("operation"),
            "producer": {"task_id": result.get("task_id"), "call_id": result.get("call_id"),
                         "agent_execution_id": result.get("agent_execution_id")},
            "row_count": result.get("row_count"), "payload_type": result.get("payload_type"),
            "source_complete": result.get("source_complete"), "revision": result.get("revision", 1),
            "sql_table": result.get("sql_ref"),
            "source_result_ids": result.get("source_result_ids") or [],
            **schema_page(result.get("observed_schema") or {}, limit=10, budget=1200),
        })
    # Tool usage belongs to the role's system/tool contract, not every data
    # inventory (including empty inventories and synthesis without tools).
    return {"items": RuntimeRedactor().redact(items), "results_status": results_status}


async def load_result_catalog(*, ctx: Any, run_id: str) -> tuple[list[dict[str, Any]], str]:
    """Load authorized metadata; a store outage must not mean 'no results'."""
    if ctx is None or not run_id or not ctx.user_id or not ctx.tenant_id:
        return [], "not_requested"
    from app.services.tool_result_store import ToolResultStore
    try:
        return await ToolResultStore().list_for_run(
            run_id=run_id, tenant_id=ctx.tenant_id, user_id=ctx.user_id), "available"
    except Exception:
        logger.exception("Could not load datastore result metadata for run_id=%s", run_id)
        return [], "unavailable"
