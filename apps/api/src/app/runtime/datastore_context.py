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


async def load_prior_result_inventory(
    *, session: Any, chat_snapshot: dict[str, Any], chat_id: str, owner_id: str,
    branch_id: str | None, tenant_id: Any, user_id: Any,
    max_source_runs: int | None = None, max_items: int | None = None,
) -> dict[str, Any]:
    """Reauthorize chat-persisted source runs and load bounded metadata only.

    Snapshot IDs in chat context are hints, never permissions. The service
    checks chat/branch ownership and Result Store user/tenant/TTL before
    returning any importable metadata. No dataset payload is loaded here.
    """
    from app.core.config import get_settings
    settings = get_settings()
    max_source_runs = max_source_runs or settings.CHAT_CONTEXT_PRIOR_RESULT_RUN_LIMIT
    max_items = max_items or settings.CHAT_CONTEXT_PRIOR_RESULT_LIMIT
    task_refs = chat_snapshot.get("task_result_refs") if isinstance(chat_snapshot, dict) else []
    selected_by_run: dict[str, list[str]] = {}
    parent_runs: list[str] = []
    for task_ref in task_refs or []:
        if not isinstance(task_ref, dict):
            continue
        parent_source = str(task_ref.get("source_run_id") or "").strip()
        if parent_source and parent_source not in parent_runs:
            parent_runs.append(parent_source)
        refs = task_ref.get("result_refs") if isinstance(task_ref.get("result_refs"), list) else []
        for ref in refs:
            source = str((ref.get("source_run_id") if isinstance(ref, dict) else None) or parent_source).strip()
            if not source:
                continue
            selected = selected_by_run.setdefault(source, [])
            result_id = str(ref.get("result_id") or "").strip() if isinstance(ref, dict) else ""
            if result_id and result_id not in selected:
                selected.append(result_id)
    requested_runs_all = list(dict.fromkeys([*parent_runs, *selected_by_run.keys()]))
    requested_runs = requested_runs_all[:max_source_runs]
    omitted_by_limit = max(0, len(requested_runs_all) - len(requested_runs))
    base = {"status": "empty", "items": [], "source_runs": [], "coverage": "complete",
            "omitted_source_runs": omitted_by_limit, "omitted_items": 0}
    if not requested_runs:
        return base
    from app.services.runtime_result_reuse_service import RuntimeResultReuseService
    service = RuntimeResultReuseService(session)
    try:
        authorized = set(await service.authorize_source_runs(
            run_ids=requested_runs, chat_id=chat_id, owner_id=owner_id, branch_id=branch_id,
        ))
    except Exception:
        logger.exception("Could not authorize prior result source runs")
        return {**base, "status": "unavailable", "coverage": "unavailable",
                "omitted_source_runs": len(requested_runs)}

    source_runs: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    unavailable_runs = len(requested_runs) - len(authorized)
    omitted_items = 0
    for source_run_id in requested_runs:
        if source_run_id not in authorized:
            continue
        selected_ids = selected_by_run.get(source_run_id, [])
        if not selected_ids:
            source_runs.append({"source_run_id": source_run_id, "status": "history_available",
                "snapshot_label": "prior turn snapshots", "history": {"tool": "result.history",
                    "arguments": {"source_run_id": source_run_id, "offset": 0, "limit": max_items}}})
            continue
        if len(items) >= max_items:
            omitted_items += 1
            continue
        try:
            page = await service.list_prior_snapshots(
                source_run_id=source_run_id, current_chat_id=chat_id, owner_id=owner_id,
                branch_id=branch_id, tenant_id=tenant_id, user_id=user_id,
                offset=0, limit=min(50, max_items - len(items)),
                selected_result_ids=selected_ids[:50],
            )
        except Exception:
            logger.exception("Could not load prior result metadata for source_run_id=%s", source_run_id)
            source_runs.append({"source_run_id": source_run_id, "status": "unavailable",
                                "history": {"tool": "result.history", "arguments": {
                                    "source_run_id": source_run_id, "offset": 0, "limit": max_items}}})
            unavailable_runs += 1
            continue
        run_items = page.get("items") if isinstance(page.get("items"), list) else []
        remaining = max_items - len(items)
        kept: list[dict[str, Any]] = []
        for raw_item in run_items[:remaining]:
            if not isinstance(raw_item, dict):
                continue
            item = {key: raw_item[key] for key in (
                "result_id", "operation", "producer", "row_count", "payload_type", "revision",
                "source_complete", "source_total", "created_at", "expires_at", "snapshot_only",
                "imported_from", "importable", "unavailable_reason",
            ) if key in raw_item}
            item["result_id"] = str(item.get("result_id") or "")[:255]
            item["operation"] = str(item.get("operation") or "unknown")[:512]
            item["source_run_id"] = source_run_id
            item["snapshot_only"] = True
            item["fresh_retrieval"] = False
            revision = item.get("revision")
            if item.get("importable") is True and isinstance(revision, int):
                item["import"] = {"tool": "result.import", "arguments": {
                    "source_run_id": source_run_id, "result_id": item["result_id"], "revision": revision,
                }}
            kept.append(item)
        omitted_items += max(0, len(run_items) - len(kept))
        for item in kept:
            items.append(item)
        source_runs.append({
            "source_run_id": source_run_id,
            "status": str(page.get("status") or "unavailable"),
            "snapshot_label": "prior turn result snapshot",
            "history": {"tool": "result.history", "arguments": {
                "source_run_id": source_run_id,
                # The history tool pages the whole source-run catalog; its
                # cursor is distinct from selected-result-ID paging above.
                "offset": 0, "limit": max_items,
            }},
            "catalog_complete": bool(page.get("catalog_complete")),
            "next_offset": page.get("next_offset"),
        })
        omitted_items += max(0, len(selected_by_run.get(source_run_id, [])) - len(run_items))
    status = ("available" if any(item.get("importable") is True for item in items)
              else "unavailable" if items or unavailable_runs else "history_available" if source_runs else "empty")
    truncated_refs = any(bool(ref.get("result_refs_truncated")) for ref in task_refs if isinstance(ref, dict))
    truncated_refs = truncated_refs or any(len(ids) > 50 for ids in selected_by_run.values())
    unavailable_items = any(item.get("importable") is False for item in items)
    coverage = "partial" if unavailable_runs or unavailable_items or omitted_items or omitted_by_limit or truncated_refs else "complete"
    return {"status": status, "items": items, "source_runs": source_runs,
            "coverage": coverage, "omitted_source_runs": unavailable_runs + omitted_by_limit,
            "omitted_items": omitted_items}
