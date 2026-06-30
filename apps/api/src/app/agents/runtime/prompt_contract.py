from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.agents.contracts import PublishedOperationSummary, ResolvedOperation


_COLLECTION_BINDING_FIELDS = frozenset({"collection_slug", "collection_id"})


def operation_requires_explicit_collection_binding(op: "ResolvedOperation") -> bool:
    return False


def build_prompt_input_schema(op: "ResolvedOperation") -> Dict[str, Any]:
    schema = deepcopy(dict(getattr(op, "input_schema", {}) or {}))
    schema.setdefault("type", "object")
    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        properties = {}
        schema["properties"] = properties

    if getattr(op, "scope", "collection") == "collection" and not operation_requires_explicit_collection_binding(op):
        for field_name in _COLLECTION_BINDING_FIELDS:
            properties.pop(field_name, None)
        required = [
            item
            for item in (schema.get("required") or [])
            if str(item).strip() not in _COLLECTION_BINDING_FIELDS
        ]
        if required:
            schema["required"] = required
        else:
            schema.pop("required", None)

    return schema


def summarize_prompt_input_schema(schema: dict | None, *, max_items: int = 4) -> list[str]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = {
        str(item).strip()
        for item in (schema.get("required") or [])
        if str(item).strip()
    }
    summary: list[str] = []
    for key, value in properties.items():
        name = str(key).strip()
        if not name:
            continue
        if len(summary) >= max_items:
            break
        field_type = ""
        if isinstance(value, dict):
            raw_type = str(value.get("type") or "").strip()
            if raw_type:
                field_type = f": {raw_type}"
        suffix = " (required)" if name in required else ""
        summary.append(f"{name}{field_type}{suffix}")
    return summary


def build_prompt_operation_description(
    op: "ResolvedOperation",
    *,
    summary: Optional["PublishedOperationSummary"] = None,
    max_chars: int = 512,
) -> str:
    title = _text(getattr(summary, "title", None)) or _text(getattr(op, "name", None)) or _text(getattr(op, "operation_slug", None))
    collection_slug = _text(getattr(summary, "collection_slug", None)) or _text(getattr(op, "collection_slug", None))
    collection_type = _text(getattr(summary, "collection_type", None))
    result_kind = _text(getattr(summary, "result_kind", None)) or _text(getattr(op, "result_kind", None))
    base_description = _text(getattr(summary, "description", None)) or _text(getattr(op, "description", None))

    parts: List[str] = [title]
    if getattr(op, "scope", "collection") == "collection":
        if collection_slug and collection_type:
            parts.append(f"bound to collection: {collection_slug} ({collection_type})")
            parts.append("runtime already binds the collection; do not pass or change collection_slug/collection_id")
        elif collection_slug:
            parts.append(f"bound to collection: {collection_slug}")
            parts.append("runtime already binds the collection; do not pass or change collection_slug/collection_id")
        else:
            parts.append("bound to collection; runtime already binds the collection")
    if base_description:
        parts.append(base_description)
    if result_kind:
        parts.append(f"result: {result_kind}")

    argument_summary = _build_argument_summary(op)
    if argument_summary:
        parts.append(argument_summary)
    usage_notes = _build_usage_notes(op)
    parts.extend(usage_notes)

    rendered = " | ".join(part for part in parts if part)
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars].rstrip()
    return rendered


def _build_usage_notes(op: "ResolvedOperation") -> List[str]:
    canonical = _text(getattr(op, "operation", None))
    notes: List[str] = []

    if canonical == "collection.info":
        notes.append("use before applying filters or guessing field values")
        notes.append("returns filterable fields and observed values/choices when available")
        return notes

    input_schema = dict(getattr(op, "input_schema", {}) or {})
    properties = input_schema.get("properties")
    if isinstance(properties, dict) and "filters" in properties:
        notes.append("use filters only on schema-declared filterable fields")
        notes.append("if filter names or values are unknown, call collection.info first")
        notes.append("do not invent filter values")

    if canonical == "collection.document.search":
        notes.append("use this first when the task asks for document contents or evidence from documents")
        notes.append("take document_id only from search/list results")
    elif canonical == "collection.document.list":
        notes.append("use this to enumerate available documents when semantic search is not needed")
    if canonical == "collection.document.get":
        notes.append("document_id must come from collection.document.search or collection.document.list")
        notes.append("use the returned file/storage reference with file.read if the document body is needed")
    elif canonical == "collection.template.list":
        notes.append("use this first to discover row_id and storage_uri")
    elif canonical == "collection.template.search":
        notes.append("use this to find the right template row by meaning before get_schema/fill")
    elif canonical == "collection.template.get_schema":
        notes.append("row_id must come from collection.template.list")
        notes.append("use this immediately before fill to get exact values keys and placeholders")
        notes.append("do not invent row_id")
    elif canonical == "collection.template.fill":
        notes.append("row_id must come from collection.template.list")
        notes.append("call collection.template.get_schema first and use the exact field keys it returns")
        notes.append("this operation already creates the final downloadable file")
        notes.append("after success, return download_url/file_id to the user and do not call file.generate")
        notes.append("do not invent row_id")
    elif canonical == "collection.sql.search_objects":
        notes.append("use this before sql execution to discover real tables, views, and columns")
    elif canonical == "collection.sql.execute":
        notes.append("run read-only SQL only after discovering the target objects")

    return notes


def _build_argument_summary(op: "ResolvedOperation") -> str:
    schema = build_prompt_input_schema(op)
    summary = summarize_prompt_input_schema(schema, max_items=6)
    if not summary:
        return "arguments: none"

    required: List[str] = []
    optional: List[str] = []
    for item in summary:
        if item.endswith("(required)"):
            required.append(item[: -len(" (required)")])
        else:
            optional.append(item)

    parts: List[str] = []
    if required:
        parts.append(f"required args: {', '.join(required)}")
    if optional:
        parts.append(f"optional args: {', '.join(optional)}")
    return " | ".join(parts)


def _text(value: Any) -> str:
    return str(value or "").strip()
