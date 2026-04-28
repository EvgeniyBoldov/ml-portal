from app.api.v1.routers.admin.collections_core import _normalize_sql_discovery_schema


def test_normalize_sql_discovery_schema_builds_schemas_payload():
    discovered = [
        {
            "schema_name": "public",
            "table_name": "tenwork_tickets",
            "table_schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title": {"type": "string"},
                },
            },
        },
        {
            "schema_name": "public",
            "table_name": "services",
            "table_schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "service_name": {"type": "string"},
                },
            },
        },
    ]

    normalized = _normalize_sql_discovery_schema(discovered)

    assert "schemas" in normalized
    schemas = normalized["schemas"]
    assert isinstance(schemas, list)
    assert len(schemas) == 1
    assert schemas[0]["schema"] == "public"
    table_names = [row["name"] for row in schemas[0]["tables"]]
    assert table_names == ["services", "tenwork_tickets"]

