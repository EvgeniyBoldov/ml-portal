"""Deterministic absence normalization shared by task validation boundaries."""
from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator


def is_absent(value: Any) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


def normalize_task_value(value: Any, schema: dict[str, Any]) -> tuple[Any, bool]:
    """Normalize absence only; never convert numbers, booleans or real text.

    Null is preferred when allowed. Otherwise use a schema-valid empty string,
    array or object. A blank optional property that allows no absent value is
    omitted. Required properties remain present and fail ordinary validation.
    All candidates are checked against the complete schema, including refs.
    """
    validator = Draft202012Validator(schema)

    def components(node_schema: Any, seen: frozenset[str] = frozenset()) -> list[dict]:
        if not isinstance(node_schema, dict):
            return []
        result = [node_schema]
        ref = node_schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/") and ref not in seen:
            target: Any = schema
            for part in ref[2:].split("/"):
                target = target.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(target, dict) else {}
            result.extend(components(target, seen | {ref}))
        for branch in node_schema.get("allOf", []):
            result.extend(components(branch, seen))
        return result

    def visit(node: Any, node_schema: Any, depth: int = 0) -> Any:
        if depth > 64:
            return node
        check = validator.evolve(schema=node_schema)
        parts = components(node_schema)
        if is_absent(node):
            candidates: list[Any] = [None]
            for part in parts:
                types = part.get("type", [])
                types = [types] if isinstance(types, str) else types
                for kind, empty in (("string", ""), ("array", []), ("object", {})):
                    if kind in types:
                        candidates.append(empty)
                for union in ("anyOf", "oneOf"):
                    for branch in part.get(union, []):
                        candidates.append(visit(node, branch, depth + 1))
            for candidate in candidates:
                if check.is_valid(candidate):
                    return candidate
            return "" if isinstance(node, str) else None

        # Union branches may have different property contracts. Select a
        # normalized branch only if it validates against the original union.
        for part in parts:
            for union in ("anyOf", "oneOf"):
                for branch in part.get(union, []):
                    sibling_parts = [dict(p) for p in parts]
                    for sibling in sibling_parts:
                        sibling.pop("anyOf", None)
                        sibling.pop("oneOf", None)
                        sibling.pop("$ref", None)
                        sibling.pop("allOf", None)
                    candidate = visit(node, {"allOf": [*sibling_parts, branch]}, depth + 1)
                    if check.is_valid(candidate):
                        return candidate

        if isinstance(node, dict):
            result = {}
            required = {key for part in parts for key in part.get("required", [])}
            for key, child in node.items():
                child_schemas = []
                for part in parts:
                    properties = part.get("properties", {})
                    matched = False
                    if key in properties:
                        child_schemas.append(properties[key])
                        matched = True
                    for pattern, pattern_schema in part.get("patternProperties", {}).items():
                        if re.search(pattern, key):
                            child_schemas.append(pattern_schema)
                            matched = True
                    if not matched:
                        child_schemas.append(part.get("additionalProperties", {}))
                if not child_schemas:
                    result[key] = child
                    continue
                child_schema = {"allOf": child_schemas}
                normalized = visit(child, child_schema, depth + 1)
                if (is_absent(child) and key not in required and all(part is not False for part in child_schemas)
                        and not validator.evolve(schema=child_schema).is_valid(normalized)):
                    continue
                result[key] = normalized
            return result
        if isinstance(node, list):
            result = []
            for index, child in enumerate(node):
                child_schemas = []
                for part in parts:
                    prefix = part.get("prefixItems", [])
                    item_schema = prefix[index] if index < len(prefix) else part.get("items", {})
                    child_schemas.append(item_schema)
                result.append(visit(child, {"allOf": child_schemas}, depth + 1))
            return result
        return node

    normalized = visit(value, schema)
    return normalized, normalized != value or type(normalized) is not type(value)


TASK_COMPLETION_RULES = """Normalization and verification rules:
completion and report are required, non-blank strings. Unknown fields and output keys are errors.
Optional envelope fields may be omitted, null, or blank: outputs -> {}, needs/coverage -> [], limitation -> null.
Every supplied output is a typed slot. Required outputs must be present for fulfilled; a missing value member is an error.
Inside value slots, null/blank text means absence: use null if the value schema permits it; otherwise a schema-valid empty string, array or object. An absent optional object property may be omitted. Required data is never invented. Zero, false, [] and {} remain values.
needs is non-empty only for completion=needs. limitation is required only for unfulfillable; absent/null/blank limitation is allowed otherwise.
needs and unfulfillable may supply partial outputs, but every supplied output must still validate.
needs refs and coverage (output_key, output_path) pairs must be unique.
Coverage proves access to data, not equality of output length to source rows: SQL can filter, group and reshape data.
If this task has any clipped stored tool result (inline_complete=false), every non-empty output array needs a coverage claim. A root claim covers all nested arrays in that value.
For SQL-derived outputs cite the saved SQL result_id and its successful SQL query_call_id. For copied select pages cite the original result_id and all successful select query_call_ids.
coverage.output_path is a dot-separated path within the value; omitted, null, or blank means the entire value. A claim also covers nested arrays. Only use observed references; SQL claims require a successfully stored complete query result; copied select claims require contiguous complete selection pages.
Source completeness is required only when the output spec sets require_complete_source=true (default false). Such outputs always require coverage referencing runtime-confirmed complete sources. Completeness of the query, source data and inline preview are different properties.
If validation fails, correct the listed paths in the same task. Do not repeat completed external actions just to repair the declaration."""
