"""
FieldCoercion — type-safe coercion and validation of collection row values.

Shared component: used by CollectionService, CollectionCSVService, and any
future importer that needs to convert raw user/API input to typed PG values.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Any, List, Optional

from app.core.exceptions import InvalidSchemaError, RowValidationError
from app.models.collection import Collection, FieldCategory, FieldType


def parse_string_bool(value: str) -> bool:
    lower = value.strip().lower()
    if lower in ("true", "1", "yes", "y", "да"):
        return True
    if lower in ("false", "0", "no", "n", "нет"):
        return False
    raise ValueError(f"Cannot parse '{value}' as boolean")


def parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Cannot parse '{value}' as datetime") from exc


def parse_date(value: str) -> date:
    normalized = value.strip()
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Cannot parse '{value}' as date") from exc


def coerce_value(field_name: str, field_type: str, value: Any) -> Any:
    """Coerce a single raw value to the target field type."""
    if value is None:
        return None

    try:
        if field_type == FieldType.STRING.value:
            return str(value)[:255]

        if field_type == FieldType.TEXT.value:
            return str(value)

        if field_type == FieldType.INTEGER.value:
            if isinstance(value, str):
                value = value.strip()
            return int(value)

        if field_type == FieldType.FLOAT.value:
            if isinstance(value, str):
                value = value.strip()
            return float(value)

        if field_type == FieldType.BOOLEAN.value:
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return bool(value)
            if isinstance(value, str):
                return parse_string_bool(value)
            raise ValueError(f"Cannot coerce {type(value).__name__} to boolean")

        if field_type == FieldType.DATETIME.value:
            if isinstance(value, datetime):
                return value
            return parse_datetime(str(value))

        if field_type == FieldType.DATE.value:
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            if isinstance(value, datetime):
                return value.date()
            return parse_date(str(value))

        if field_type in (FieldType.ENUM.value,):
            return str(value)[:100]

        if field_type in (FieldType.JSON.value, FieldType.FILE.value):
            if isinstance(value, (dict, list)):
                return value
            import json as _json
            try:
                return _json.loads(value)
            except Exception:
                raise ValueError(f"Cannot parse '{field_name}' as JSON")

        return value

    except (ValueError, TypeError) as exc:
        raise RowValidationError(
            f"Field '{field_name}': cannot coerce value to {field_type}: {exc}"
        ) from exc


def validate_and_prepare_payload(
    collection: Collection,
    payload: dict,
    partial: bool = False,
) -> dict:
    """
    Validate and type-coerce a row payload against the collection schema.

    - partial=False: all required fields must be present (CREATE)
    - partial=True: only provided fields are coerced (PATCH)

    Returns a prepared dict with coerced values, ready for SQL insert/update.
    Raises RowValidationError for any validation failure.
    """
    writable_fields: List[dict] = collection.get_row_writable_fields()
    field_map = {f["name"]: f for f in writable_fields}
    prepared: dict = {}

    unknown_fields = set(payload.keys()) - set(field_map.keys())
    if unknown_fields:
        raise RowValidationError(
            f"Unknown fields: {', '.join(sorted(unknown_fields))}"
        )

    for field_def in writable_fields:
        field_name: str = field_def["name"]
        field_type: str = field_def.get("data_type", FieldType.STRING.value)
        is_required: bool = field_def.get("required", False)
        if field_name not in payload:
            if partial:
                continue
            if is_required:
                raise RowValidationError(f"Required field '{field_name}' is missing")
            continue

        value = payload[field_name]
        prepared[field_name] = coerce_value(field_name, field_type, value)

    return prepared
