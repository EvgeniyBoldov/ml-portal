"""Infer and persist structural schemas for observed tool data."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovered_tool import DiscoveredTool


def infer_data_schema(value: Any) -> dict[str, Any]:
    """Return a value-free JSON Schema describing the observed data shape."""
    return _infer(value)


def _infer(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {str(key): _infer(item) for key, item in value.items()},
        }
    if isinstance(value, list):
        item_schema: dict[str, Any] = {}
        for item in value:
            item_schema = _merge(item_schema, _infer(item))
        return {"type": "array", "items": item_schema}
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    return {}


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Merge observed variants without copying any source values."""
    if not left:
        return right
    if not right:
        return left
    if left.get("type") == right.get("type") == "object":
        left_properties = left.get("properties") or {}
        right_properties = right.get("properties") or {}
        properties = {
            key: _merge(left_properties[key], right_properties[key])
            if key in left_properties and key in right_properties
            else left_properties.get(key, right_properties.get(key, {}))
            for key in dict.fromkeys((*left_properties.keys(), *right_properties.keys()))
        }
        return {"type": "object", "properties": properties}
    if left.get("type") == right.get("type") == "array":
        return {"type": "array", "items": _merge(left.get("items") or {}, right.get("items") or {})}
    if left == right:
        return left

    variants: list[dict[str, Any]] = []
    for candidate in (*left.get("anyOf", [left]), *right.get("anyOf", [right])):
        if candidate not in variants:
            variants.append(candidate)
    return {"anyOf": variants}


async def save_observed_schema_if_missing(
    session: AsyncSession,
    *,
    discovered_tool_id: UUID,
    schema: dict[str, Any],
) -> bool:
    """Store only the first inferred schema; never persist the tool payload."""
    result = await session.execute(
        update(DiscoveredTool)
        .where(
            DiscoveredTool.id == discovered_tool_id,
            DiscoveredTool.observed_data_schema.is_(None),
        )
        .values(observed_data_schema=schema)
    )
    return bool(result.rowcount)
