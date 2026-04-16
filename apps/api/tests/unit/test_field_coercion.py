"""
Unit tests for services/collection/field_coercion.py

Tests coerce_value and validate_and_prepare_payload — pure functions,
no DB required.
"""
import pytest
from datetime import datetime, date
from unittest.mock import MagicMock

from app.services.collection.field_coercion import (
    coerce_value,
    parse_string_bool,
    parse_datetime,
    parse_date,
    validate_and_prepare_payload,
)
from app.core.exceptions import RowValidationError


# ── parse_string_bool ─────────────────────────────────────────────────────────

class TestParseStringBool:
    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "y", "да"])
    def test_truthy_values(self, value):
        assert parse_string_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "n", "нет"])
    def test_falsy_values(self, value):
        assert parse_string_bool(value) is False

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_string_bool("maybe")


# ── parse_datetime ────────────────────────────────────────────────────────────

class TestParseDatetime:
    def test_iso_format(self):
        result = parse_datetime("2024-01-15T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2024

    def test_z_suffix(self):
        result = parse_datetime("2024-01-15T10:30:00Z")
        assert result.tzinfo is not None

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_datetime("not-a-date")


# ── parse_date ────────────────────────────────────────────────────────────────

class TestParseDate:
    def test_iso_format(self):
        result = parse_date("2024-03-20")
        assert isinstance(result, date)
        assert result.month == 3

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_date("20/03/2024")


# ── coerce_value ──────────────────────────────────────────────────────────────

class TestCoerceValue:
    def test_none_passthrough(self):
        assert coerce_value("f", "string", None) is None

    def test_string_truncated(self):
        result = coerce_value("f", "string", "x" * 300)
        assert len(result) == 255

    def test_text_not_truncated(self):
        long = "x" * 300
        assert coerce_value("f", "text", long) == long

    def test_integer_from_string(self):
        assert coerce_value("f", "integer", "42") == 42

    def test_float_from_string(self):
        assert coerce_value("f", "float", "3.14") == pytest.approx(3.14)

    def test_boolean_from_bool(self):
        assert coerce_value("f", "boolean", True) is True

    def test_boolean_from_string(self):
        assert coerce_value("f", "boolean", "yes") is True

    def test_datetime_passthrough(self):
        dt = datetime(2024, 1, 1)
        assert coerce_value("f", "datetime", dt) == dt

    def test_datetime_from_string(self):
        result = coerce_value("f", "datetime", "2024-01-01T00:00:00")
        assert isinstance(result, datetime)

    def test_date_from_string(self):
        result = coerce_value("f", "date", "2024-06-15")
        assert isinstance(result, date)

    def test_json_dict_passthrough(self):
        d = {"key": "value"}
        assert coerce_value("f", "json", d) == d

    def test_json_from_string(self):
        result = coerce_value("f", "json", '{"a": 1}')
        assert result == {"a": 1}

    def test_invalid_int_raises_row_validation_error(self):
        with pytest.raises(RowValidationError):
            coerce_value("num", "integer", "not-a-number")

    def test_invalid_json_raises_row_validation_error(self):
        with pytest.raises(RowValidationError):
            coerce_value("data", "json", "{broken")


# ── validate_and_prepare_payload ──────────────────────────────────────────────

def _make_collection(fields: list) -> MagicMock:
    col = MagicMock()
    col.get_row_writable_fields.return_value = fields
    col.fields = fields
    return col


class TestValidateAndPreparePayload:
    def _fields(self):
        return [
            {"name": "title", "data_type": "string", "required": True, "category": "user"},
            {"name": "count", "data_type": "integer", "required": False, "category": "user"},
        ]

    def test_full_create(self):
        col = _make_collection(self._fields())
        result = validate_and_prepare_payload(col, {"title": "Hello", "count": "5"})
        assert result["title"] == "Hello"
        assert result["count"] == 5

    def test_partial_skip_missing(self):
        col = _make_collection(self._fields())
        result = validate_and_prepare_payload(col, {"count": "3"}, partial=True)
        assert "title" not in result
        assert result["count"] == 3

    def test_unknown_field_raises(self):
        col = _make_collection(self._fields())
        with pytest.raises(RowValidationError, match="Unknown"):
            validate_and_prepare_payload(col, {"title": "x", "ghost": "y"})

    def test_missing_required_raises(self):
        col = _make_collection(self._fields())
        with pytest.raises(RowValidationError, match="missing"):
            validate_and_prepare_payload(col, {"count": "1"}, partial=False)

    def test_specific_category_skipped(self):
        fields = [
            {"name": "title", "data_type": "string", "required": True, "category": "user"},
            {"name": "_sys", "data_type": "text", "required": False, "category": "specific"},
        ]
        col = _make_collection(fields)
        result = validate_and_prepare_payload(col, {"title": "Test"})
        assert "_sys" not in result
