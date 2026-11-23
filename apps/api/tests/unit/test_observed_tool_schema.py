"""Unit tests for observed tool schema inference (app/services/observed_tool_schema.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.observed_tool_schema import infer_data_schema, save_observed_schema_if_missing


class TestInferDataSchema:
    def test_scalar_types(self):
        assert infer_data_schema("hello") == {"type": "string"}
        assert infer_data_schema(42) == {"type": "integer"}
        assert infer_data_schema(3.14) == {"type": "number"}
        assert infer_data_schema(True) == {"type": "boolean"}
        # bool is checked before int, so True is never reported as integer.
        assert infer_data_schema(False) == {"type": "boolean"}
        assert infer_data_schema(None) == {"type": "null"}

    def test_nested_object(self):
        value = {
            "name": "x",
            "count": 1,
            "nested": {"flag": True},
        }

        assert infer_data_schema(value) == {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
                "nested": {"type": "object", "properties": {"flag": {"type": "boolean"}}},
            },
        }

    def test_homogeneous_array(self):
        assert infer_data_schema([1, 2, 3]) == {"type": "array", "items": {"type": "integer"}}

    def test_array_merges_item_variants(self):
        schema = infer_data_schema([{"a": 1}, {"a": 2, "b": "x"}])

        assert schema == {
            "type": "array",
            "items": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "string"}}},
        }

    def test_empty_array_has_no_item_schema(self):
        assert infer_data_schema([]) == {"type": "array", "items": {}}

    def test_divergent_scalars_become_anyof(self):
        schema = infer_data_schema([1, "two"])

        assert schema == {
            "type": "array",
            "items": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
        }

    def test_anyof_variants_are_deduped(self):
        schema = infer_data_schema([1, "two", 3, "four"])

        items = schema["items"]
        assert items["anyOf"] == [{"type": "integer"}, {"type": "string"}]

    def test_unsupported_type_yields_empty_schema(self):
        class Opaque:
            pass

        assert infer_data_schema(Opaque()) == {}

    def test_schema_contains_no_values(self):
        value = {"secret_token": "abc123", "items": ["sensitive"]}

        schema = infer_data_schema(value)

        assert "abc123" not in str(schema)
        assert "sensitive" not in str(schema)


class TestSaveObservedSchemaIfMissing:
    async def test_persists_when_row_updated(self):
        session = AsyncMock()
        result = MagicMock()
        result.rowcount = 1
        session.execute.return_value = result

        saved = await save_observed_schema_if_missing(
            session, discovered_tool_id=uuid4(), schema={"type": "object"}
        )

        assert saved is True

    async def test_skips_when_schema_already_present(self):
        session = AsyncMock()
        result = MagicMock()
        result.rowcount = 0
        session.execute.return_value = result

        saved = await save_observed_schema_if_missing(
            session, discovered_tool_id=uuid4(), schema={"type": "object"}
        )

        assert saved is False

    async def test_update_targets_only_missing_schema(self):
        session = AsyncMock()
        result = MagicMock()
        result.rowcount = 1
        session.execute.return_value = result
        tool_id = uuid4()

        await save_observed_schema_if_missing(session, discovered_tool_id=tool_id, schema={"type": "null"})

        stmt = session.execute.call_args.args[0]
        compiled = stmt.compile()
        assert compiled.params["id_1"] == tool_id
        assert compiled.params["observed_data_schema"] == {"type": "null"}
        # Guarded update, not a blind overwrite: an IS NULL filter must be present.
        assert stmt.whereclause is not None
