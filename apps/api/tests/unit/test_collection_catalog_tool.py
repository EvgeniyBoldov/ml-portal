from types import SimpleNamespace

from app.agents.builtins.collection_catalog import CollectionCatalogTool


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

    tables = CollectionCatalogTool._extract_remote_tables(table_schema, source_contract)

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
    allowed = CollectionCatalogTool._resolve_allowed_dimensions(collection)
    assert allowed == {"vendor", "priority"}
