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


def test_to_jsonb_returns_hierarchical_schema():
    c = TemplateContract(
        format=DocumentFormat.EXCEL,
        fields=[
            make_scalar("author.name"),
            make_scalar("author.tel", required=False),
            TableField(
                key="connections",
                label="Connections",
                required=False,
                columns=[
                    TableColumn(key="source.host", label="Host", type=FieldType.STRING, required=False),
                    TableColumn(key="source.ip", label="IP", type=FieldType.STRING, required=False),
                    TableColumn(key="destination.host", label="Host", type=FieldType.STRING, required=False),
                ],
            ),
        ],
        node_meta={
            "author": {"kind": "object", "label": "Author", "source": "parser", "locked": False},
            "connections.source": {"kind": "object", "label": "Source", "source": "parser", "locked": False},
            "connections.destination": {"kind": "object", "label": "Destination", "source": "parser", "locked": False},
        },
    )

    dumped = c.to_jsonb()

    assert dumped["fields"][0]["key"] == "author"
    assert dumped["fields"][0]["kind"] == "object"
    assert [field["key"] for field in dumped["fields"][0]["fields"]] == ["name", "tel"]
    table = next(field for field in dumped["fields"] if field["key"] == "connections")
    assert table["kind"] == "table"
    source = next(field for field in table["fields"] if field["key"] == "source")
    assert source["kind"] == "object"
    assert [field["key"] for field in source["fields"]] == ["host", "ip"]


def test_model_validate_accepts_hierarchical_schema():
    raw = {
        "contract_version": "1.0",
        "format": "excel",
        "fields": [
            {
                "key": "author",
                "kind": "object",
                "label": "Author",
                "fields": [
                    {"key": "name", "kind": "scalar", "label": "Name", "type": "string", "required": True},
                    {"key": "tel", "kind": "scalar", "label": "Tel", "type": "string", "required": False},
                ],
            },
            {
                "key": "connections",
                "kind": "table",
                "label": "Connections",
                "fields": [
                    {
                        "key": "source",
                        "kind": "object",
                        "label": "Source",
                        "fields": [
                            {"key": "host", "kind": "scalar", "label": "Host", "type": "string", "required": True},
                            {"key": "ip", "kind": "scalar", "label": "IP", "type": "string", "required": True},
                        ],
                    },
                    {"key": "traffic", "kind": "scalar", "label": "Traffic", "type": "string", "required": False},
                ],
            },
        ],
    }

    contract = TemplateContract.model_validate(raw)

    assert contract.get_field("author.name") is not None
    assert contract.get_field("author.tel") is not None
    table = contract.get_field("connections")
    assert isinstance(table, TableField)
    assert [column.key for column in table.columns] == ["source.host", "source.ip", "traffic"]


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


def test_fill_schema_nested_scalar():
    c = TemplateContract(fields=[make_scalar("author.email")])
    schema = c.to_fill_input_schema()
    assert schema["properties"]["author"]["type"] == "object"
    assert schema["properties"]["author"]["properties"]["email"]["type"] == "string"
    assert "author" in schema["required"]
    assert "email" in schema["properties"]["author"]["required"]


def test_fill_schema_min_items():
    c = TemplateContract(fields=[make_table("rows", min_rows=2)])
    schema = c.to_fill_input_schema()
    assert schema["properties"]["rows"]["minItems"] == 2


def test_fill_schema_max_items():
    c = TemplateContract(fields=[make_table("rows", max_rows=10)])
    schema = c.to_fill_input_schema()
    assert schema["properties"]["rows"]["maxItems"] == 10


def test_runtime_schema_preserves_nested_objects():
    c = TemplateContract(fields=[
        make_scalar("author.name"),
        make_scalar("author.tel", required=False),
        TableField(
            key="connections",
            label="Connections",
            required=True,
            columns=[
                TableColumn(key="source.host", label="Host", type=FieldType.STRING, required=True),
                TableColumn(key="source.ip", label="IP", type=FieldType.STRING, required=True),
            ],
        ),
    ])
    schema = c.to_runtime_schema()
    assert schema["properties"]["author"]["type"] == "object"
    assert "name" in schema["properties"]["author"]["properties"]
    assert schema["properties"]["connections"]["type"] == "array"
    items = schema["properties"]["connections"]["items"]
    assert items["properties"]["source"]["type"] == "object"
    assert "host" in items["properties"]["source"]["properties"]
    assert "ip" in items["properties"]["source"]["properties"]


def test_build_values_model_validates_nested_payload():
    c = TemplateContract(fields=[
        make_scalar("author.name"),
        TableField(
            key="connections",
            label="Connections",
            required=True,
            columns=[
                TableColumn(key="source.host", label="Host", type=FieldType.STRING, required=True),
                TableColumn(key="source.ip", label="IP", type=FieldType.STRING, required=True),
                TableColumn(key="traffic", label="Traffic", type=FieldType.ENUM, enum=["tcp", "udp"], required=True),
            ],
        ),
    ])
    model_cls = c.build_values_model()
    validated = model_cls.model_validate(
        {
            "author": {"name": "Alice"},
            "connections": [{"source": {"host": "gw", "ip": "10.0.0.1"}, "traffic": "tcp"}],
        }
    )
    dumped = validated.model_dump(mode="python")
    assert dumped["author"]["name"] == "Alice"
    assert dumped["connections"][0]["source"]["host"] == "gw"


def test_validate_generated_values_reports_nested_errors():
    c = TemplateContract(fields=[
        make_scalar("author.name"),
        TableField(
            key="connections",
            label="Connections",
            required=True,
            columns=[
                TableColumn(key="source.host", label="Host", type=FieldType.STRING, required=True),
                TableColumn(key="source.ip", label="IP", type=FieldType.STRING, required=True),
            ],
        ),
    ])
    report = c.validate_generated_values(
        {
            "author": {},
            "connections": [{"source": {"host": "gw"}}],
        }
    )
    assert not report.ok
    assert any("author.name" in error or "author.name" in error.replace(" ", "") for error in report.errors)
    assert any("connections" in error and "source.ip" in error for error in report.errors)
    assert any(issue.path == "author.name" and issue.rule for issue in report.error_details)
    assert any(issue.path == "connections[0].source.ip" for issue in report.error_details)


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


def test_validate_missing_required_scalar_non_strict():
    c = TemplateContract(fields=[make_scalar("name")])
    r = c.validate_values({}, enforce_required=False)
    assert r.ok


def test_validate_empty_string_scalar():
    c = TemplateContract(fields=[make_scalar("name")])
    r = c.validate_values({"name": "   "})
    assert not r.ok


def test_validate_optional_scalar_absent_ok():
    c = TemplateContract(fields=[make_scalar("note", required=False)])
    r = c.validate_values({})
    assert r.ok


def test_validate_nested_scalar_ok():
    c = TemplateContract(fields=[make_scalar("author.email")])
    r = c.validate_values({"author": {"email": "alice@example.com"}})
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


def test_validate_table_missing_required_column_non_strict():
    c = TemplateContract(fields=[make_table("items")])
    r = c.validate_values({"items": [{"name": "A"}]}, enforce_required=False)
    assert r.ok


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


def test_discriminated_union_table_from_dict():
    data = {
        "contract_version": "1.0",
        "fields": [{
            "key": "items", "kind": "table", "label": "Items",
            "columns": [
                {"key": "name", "label": "Name", "type": "string", "required": True},
                {"key": "qty", "label": "Qty", "type": "number", "required": True},
            ],
        }],
    }
    c = TemplateContract.model_validate(data)
    assert isinstance(c.fields[0], TableField)
    assert len(c.fields[0].columns) == 2


def test_round_trip_table_preserves_columns_via_validate():
    c = TemplateContract(fields=[make_table("rows")])
    restored = TemplateContract.model_validate(c.to_jsonb())
    assert isinstance(restored.fields[0], TableField)
    assert len(restored.fields[0].columns) == 2


def test_validate_bool_rejected_as_number():
    c = TemplateContract(fields=[
        ScalarField(key="amount", label="Amount", type=FieldType.NUMBER, required=True)
    ])
    assert not c.validate_values({"amount": True}).ok


def test_merge_preserves_existing_order():
    existing = TemplateContract(fields=[make_scalar("a"), make_scalar("b"), make_scalar("c")])
    proposed = TemplateContract(fields=[
        make_scalar("c"), make_scalar("a"), make_scalar("b"), make_scalar("d"),
    ])
    merged = merge_contract(existing, proposed)
    assert [f.key for f in merged.fields] == ["a", "b", "c", "d"]
