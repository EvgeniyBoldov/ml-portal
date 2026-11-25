"""Project locally validated schemas for OpenAI-compatible grammar backends."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


# Older llama.cpp grammar parsers reject repetitions at and above this bound.
_GRAMMAR_REPETITION_THRESHOLD = 2000
_SCHEMA_MAPS = ("$defs", "definitions", "properties", "patternProperties", "dependentSchemas")
_SCHEMA_CHILDREN = (
    "items", "additionalItems", "additionalProperties", "propertyNames", "then", "else",
    "anyOf", "allOf", "prefixItems", "unevaluatedItems", "unevaluatedProperties",
)
_PRESERVED_BRANCHES = ("not", "oneOf", "if", "contains")


def project_provider_schema(schema: dict[str, Any] | bool) -> dict[str, Any] | bool:
    """Omit unsupported grammar bounds when local validation owns the contract."""
    if isinstance(schema, bool):
        return schema

    projected = deepcopy(schema)
    pending: list[tuple[object, bool]] = [(projected, False)]
    while pending:
        node, preserve = pending.pop()
        if isinstance(node, list):
            pending.extend((child, preserve) for child in node)
            continue
        if not isinstance(node, dict):
            continue
        # Changing a definition referenced from a preserved branch can still
        # change which instances match that branch.
        if preserve and any(key in node for key in ("$ref", "$dynamicRef", "$recursiveRef")):
            return schema
        length = node.get("maxLength")
        if not preserve and type(length) is int and length >= _GRAMMAR_REPETITION_THRESHOLD:
            del node["maxLength"]
        for key in _SCHEMA_MAPS:
            children = node.get(key)
            if isinstance(children, dict):
                pending.extend((child, preserve) for child in children.values())
        pending.extend((node[key], preserve) for key in _SCHEMA_CHILDREN if key in node)
        pending.extend((node[key], True) for key in _PRESERVED_BRANCHES if key in node)
    return projected
