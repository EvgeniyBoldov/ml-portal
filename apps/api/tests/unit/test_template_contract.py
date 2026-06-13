"""Unit tests for TemplateContract (S0)."""
from __future__ import annotations

import pytest

from app.services.collection.template_contract import (
    AnchorStrategy,
    DocumentFormat,
    FieldKind,
    FieldSource,
    FieldType,
    MarkerAnchor,
    Orientation,
    ScalarField,
    StructuralAnchor,
    TableAnchor,
    TableColumn,
    TableField,
    TemplateContract,
    TokenLocator,
    ValidationReport,
    merge_contract,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_scalar(key="name", required=True, locked=False, source=FieldSource.LLM) -> ScalarField:
    return ScalarField(
        key=key,
        label=key.capitalize(),
        type=FieldType.STRING,
        required=required,
        locked=locked,
        source=source,
        locator=TokenLocator(token=f"{{{{{key}}}}}"),
    )


def make_table(key="items", cols=None, min_rows=1, max_rows=None) -> TableField:
    if cols is None:
        cols = [
            TableColumn(key="name", label="Name", type=FieldType.STRING, required=True),
            TableColumn(key="qty", label="Qty", type=FieldType.NUMBER, required=True),
        ]
    return TableField(
        key=key,
        label=key.capitalize(),
        orientation=Orientation.VERTICAL,
        required=True,
        min_rows=min_rows,
        max_rows=max_rows,
        columns=cols,
    )


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_scalar():
    c = TemplateContract(format=DocumentFormat.EXCEL, fields=[make_scalar()])
    restored = TemplateContract.model_validate(c.to_jsonb())
    assert restored.format == DocumentFormat.EXCEL
    assert len(restored.fields) == 1
    assert restored.fields[0].key == "name"


def test_round_trip_table():
    c = TemplateContract(format=DocumentFormat.DOCX, fields=[make_table()])
    restored = TemplateContract.model_validate(c.to_jsonb())
    assert restored.fields[0].kind == FieldKind.TABLE
    assert len(restored.fields[0].columns) == 2


def test_from_jsonb_old_format_returns_empty():
    old = {"format": "excel", "sheets": [], "placeholders": []}
    c = TemplateContract.from_jsonb(old)
    assert c.fields == []


def test_from_jsonb_none_returns_empty():
    c = TemplateContract.from_jsonb(None)
    assert c.fields == []


def test_from_jsonb_invalid_returns_empty():
    c = TemplateContract.from_jsonb({"contract_version": "1.0", "fields": "bad"})
    assert c.fields == []


# ---------------------------------------------------------------------------
# to_fill_input_schema
# ---------------------------------------------------------------------------


def test_fill_schema_scalar():
    c = TemplateContract(fields=[make_scalar("applicant")])
    schema = c.to_fill_input_schema()
    assert schema["type"] == "object"
    assert "applicant" in schema["properties"]
    assert schema["properties"]["applicant"]["type"] == "string"
    assert "applicant" in schema["required"]


def test_fill_schema_optional_scalar():
    c = TemplateContract(fields=[make_scalar("note", required=False)])
    schema = c.to_fill_input_schema()
    assert "note" in schema["properties"]
    assert "required" not in schema or "note" not in schema.get("required", [])


def test_fill_schema_table():
    c = TemplateContract(fields=[make_table("lines")])
    schema = c.to_fill_input_schema()
    assert schema["properties"]["lines"]["type"] == "array"
    item = schema["properties"]["lines"]["items"]
    assert "name" in item["properties"]
    assert "qty" in item["properties"]
    assert "name" in item["required"]


def test_fill_schema_mixed():
    c = TemplateContract(fields=[make_scalar("org"), make_table("positions")])
    schema = c.to_fill_input_schema()
    assert "org" in schema["properties"]
    assert "positions" in schema["properties"]
    assert schema["properties"]["positions"]["type"] == "array"


def test_fill_schema_min_items():
    c = TemplateContract(fields=[make_table("rows", min_rows=2)])
    schema = c.to_fill_input_schema()
    assert schema["properties"]["rows"]["minItems"] == 2


def test_fill_schema_max_items():
    c = TemplateContract(fields=[make_table("rows", max_rows=10)])
    schema = c.to_fill_input_schema()
    assert schema["properties"]["rows"]["maxItems"] == 10


# ---------------------------------------------------------------------------
# validate_values
# ---------------------------------------------------------------------------


def test_validate_ok_scalar():
    c = TemplateContract(fields=[make_scalar("name")])
    r = c.validate_values({"name": "Alice"})
    assert r.ok


def test_validate_missing_required_scalar():
    c = TemplateContract(fields=[make_scalar("name")])
    r = c.validate_values({})
    assert not r.ok
    assert any("name" in e for e in r.errors)


def test_validate_empty_string_scalar():
    c = TemplateContract(fields=[make_scalar("name")])
    r = c.validate_values({"name": "   "})
    assert not r.ok


def test_validate_optional_scalar_absent_ok():
    c = TemplateContract(fields=[make_scalar("note", required=False)])
    r = c.validate_values({})
    assert r.ok


def test_validate_number_type():
    c = TemplateContract(fields=[
        ScalarField(key="amount", label="Amount", type=FieldType.NUMBER, required=True)
    ])
    assert c.validate_values({"amount": 42}).ok
    assert c.validate_values({"amount": "3.14"}).ok
    assert not c.validate_values({"amount": "abc"}).ok


def test_validate_table_ok():
    c = TemplateContract(fields=[make_table("items")])
    r = c.validate_values({"items": [{"name": "A", "qty": 1}, {"name": "B", "qty": 2}]})
    assert r.ok


def test_validate_table_missing():
    c = TemplateContract(fields=[make_table("items")])
    r = c.validate_values({})
    assert not r.ok
    assert any("items" in e for e in r.errors)


def test_validate_table_not_list():
    c = TemplateContract(fields=[make_table("items")])
    r = c.validate_values({"items": "not-a-list"})
    assert not r.ok


def test_validate_table_min_rows():
    c = TemplateContract(fields=[make_table("items", min_rows=2)])
    r = c.validate_values({"items": [{"name": "A", "qty": 1}]})
    assert not r.ok
    assert any("min_rows" in e for e in r.errors)


def test_validate_table_max_rows():
    c = TemplateContract(fields=[make_table("items", max_rows=2)])
    r = c.validate_values({"items": [{"name": "A", "qty": 1}] * 5})
    assert not r.ok
    assert any("max_rows" in e for e in r.errors)


def test_validate_table_missing_required_column():
    c = TemplateContract(fields=[make_table("items")])
    r = c.validate_values({"items": [{"name": "A"}]})  # missing qty
    assert not r.ok
    assert any("qty" in e for e in r.errors)


def test_validate_unknown_key_is_warning():
    c = TemplateContract(fields=[make_scalar("name")])
    r = c.validate_values({"name": "X", "extra": "Y"})
    assert r.ok
    assert any("extra" in w for w in r.warnings)


def test_raise_if_invalid():
    c = TemplateContract(fields=[make_scalar("name")])
    r = c.validate_values({})
    with pytest.raises(ValueError, match="name"):
        r.raise_if_invalid()


# ---------------------------------------------------------------------------
# merge_contract
# ---------------------------------------------------------------------------


def test_merge_adds_new_field():
    existing = TemplateContract(fields=[make_scalar("name")])
    proposed = TemplateContract(fields=[make_scalar("name"), make_scalar("email")])
    merged = merge_contract(existing, proposed)
    keys = [f.key for f in merged.fields]
    assert "email" in keys


def test_merge_updates_llm_field():
    old_field = ScalarField(key="note", label="old", type=FieldType.STRING, source=FieldSource.LLM)
    new_field = ScalarField(key="note", label="updated", type=FieldType.STRING, source=FieldSource.LLM)
    existing = TemplateContract(fields=[old_field])
    proposed = TemplateContract(fields=[new_field])
    merged = merge_contract(existing, proposed)
    f = next(f for f in merged.fields if f.key == "note")
    assert f.label == "updated"


def test_merge_preserves_locked_field():
    locked = ScalarField(key="code", label="Code", type=FieldType.STRING, locked=True, source=FieldSource.ADMIN)
    proposed_field = ScalarField(key="code", label="OVERWRITE", type=FieldType.STRING, source=FieldSource.LLM)
    existing = TemplateContract(fields=[locked])
    proposed = TemplateContract(fields=[proposed_field])
    merged = merge_contract(existing, proposed)
    f = next(f for f in merged.fields if f.key == "code")
    assert f.label == "Code"
    assert f.locked is True


def test_merge_preserves_admin_source_field():
    admin = ScalarField(key="org", label="Org", type=FieldType.STRING, locked=False, source=FieldSource.ADMIN)
    proposed_field = ScalarField(key="org", label="OVERWRITE", type=FieldType.STRING, source=FieldSource.LLM)
    existing = TemplateContract(fields=[admin])
    proposed = TemplateContract(fields=[proposed_field])
    merged = merge_contract(existing, proposed)
    f = next(f for f in merged.fields if f.key == "org")
    assert f.label == "Org"


def test_merge_removes_vanished_llm_field():
    existing = TemplateContract(fields=[make_scalar("gone"), make_scalar("stays")])
    proposed = TemplateContract(fields=[make_scalar("stays")])
    merged = merge_contract(existing, proposed)
    keys = [f.key for f in merged.fields]
    assert "gone" not in keys
    assert "stays" in keys


def test_merge_updates_format():
    existing = TemplateContract(format=DocumentFormat.TEXT)
    proposed = TemplateContract(format=DocumentFormat.EXCEL)
    merged = merge_contract(existing, proposed)
    assert merged.format == DocumentFormat.EXCEL


# ---------------------------------------------------------------------------
# Anchor validation
# ---------------------------------------------------------------------------


def test_anchor_strategy_marker_requires_marker():
    with pytest.raises(Exception):
        TableAnchor(strategy=AnchorStrategy.MARKER, marker=None)


def test_anchor_strategy_structural_requires_structural():
    with pytest.raises(Exception):
        TableAnchor(strategy=AnchorStrategy.STRUCTURAL, structural=None)


def test_anchor_auto_no_data_is_ok():
    a = TableAnchor(strategy=AnchorStrategy.AUTO)
    assert a.strategy == AnchorStrategy.AUTO


# ---------------------------------------------------------------------------
# Enum field validation
# ---------------------------------------------------------------------------


def test_enum_type_with_enum_list():
    f = ScalarField(key="status", label="Status", type=FieldType.ENUM, enum=["A", "B"])
    assert f.enum == ["A", "B"]


def test_enum_list_without_type_raises():
    with pytest.raises(Exception):
        ScalarField(key="status", label="Status", type=FieldType.STRING, enum=["A", "B"])


# ---------------------------------------------------------------------------
# get_field / scalar_fields / table_fields helpers
# ---------------------------------------------------------------------------


def test_get_field():
    c = TemplateContract(fields=[make_scalar("x"), make_table("rows")])
    assert c.get_field("x") is not None
    assert c.get_field("missing") is None


def test_scalar_fields_and_table_fields():
    c = TemplateContract(fields=[make_scalar("x"), make_table("rows"), make_scalar("y")])
    assert len(c.scalar_fields()) == 2
    assert len(c.table_fields()) == 1
