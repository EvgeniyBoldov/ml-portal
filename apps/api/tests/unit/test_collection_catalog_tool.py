from types import SimpleNamespace

from app.agents.builtins.collection_catalog import CollectionInfoTool


def test_extract_remote_tables_from_mixed_schema_shapes():
    table_schema = {
        "tables": [
            {"schema": "public", "name": "vendors", "columns": [{"name": "id"}, {"name": "name"}]},
            "tickets",
        ],
        "schemas": {
            "netbox": ["devices", {"name": "interfaces", "columns": [{"name": "id"}]}],
        },
    }
    source_contract = {
        "schemas": [
            {"schema": "public", "tables": ["vendors", {"name": "contracts"}]},
        ]
    }

    tables = CollectionInfoTool._extract_remote_tables(table_schema, source_contract)

    assert {"schema": "public", "table": "vendors", "columns_count": 2} in tables
    assert {"schema": None, "table": "tickets", "columns_count": None} in tables
    assert {"schema": "netbox", "table": "devices", "columns_count": None} in tables
    assert {"schema": "public", "table": "contracts", "columns_count": None} in tables


def test_resolve_allowed_dimensions_skips_file_and_json():
    collection = SimpleNamespace(
        get_business_fields=lambda: [
            {"name": "vendor", "data_type": "string"},
            {"name": "tags", "data_type": "json"},
            {"name": "file", "data_type": "file"},
            {"name": "priority", "data_type": "integer"},
        ]
    )
    allowed = CollectionInfoTool._resolve_allowed_dimensions(collection)
    assert allowed == {"vendor", "priority"}


def test_resolve_dimensions_to_inspect_defaults_to_filterable_fields_for_document_collections():
    collection = SimpleNamespace(
        collection_type="document",
        get_filterable_fields=lambda: [
            {"name": "vendor", "filterable": True},
            {"name": "severity", "filterable": True},
            {"name": "blob", "filterable": True},
        ],
    )

    dimensions = CollectionInfoTool._resolve_dimensions_to_inspect(
        collection=collection,
        requested_dimensions=[],
        allowed_dimensions={"vendor", "severity"},
    )

    assert dimensions == ["severity", "vendor"]


def test_resolve_dimensions_to_inspect_respects_requested_dimensions_subset():
    collection = SimpleNamespace(
        collection_type="document",
        get_filterable_fields=lambda: [{"name": "vendor", "filterable": True}],
    )

    dimensions = CollectionInfoTool._resolve_dimensions_to_inspect(
        collection=collection,
        requested_dimensions=["vendor", "missing"],
        allowed_dimensions={"vendor"},
    )

    assert dimensions == ["vendor"]


def test_build_filter_hint_note_is_explicit_about_non_guessing():
    assert "Use only values listed" in CollectionInfoTool._build_filter_hint_note(
        collection_type="document",
        field_name="vendor",
        coverage="complete",
    )
    assert "Do not invent values" in CollectionInfoTool._build_filter_hint_note(
        collection_type="document",
        field_name="vendor",
        coverage="top_values",
    )
    assert "Do not guess values" in CollectionInfoTool._build_filter_hint_note(
        collection_type="document",
        field_name="vendor",
        coverage="none",
    )
