from types import SimpleNamespace

import pytest

from app.agents.builtins.collection_catalog import CollectionInfoTool
from app.agents.context import RuntimeDependencies
from app.agents.contracts import ResolvedOperation
from app.services.collection_info_service import build_default_collection_info_response_builder


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


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    async def execute(self, stmt, params=None):
        query = str(stmt)
        if "COUNT(*)::bigint FROM template_rows" in query and "IS NULL" not in query and "DISTINCT" not in query:
            return _FakeResult([{"count": 3}])
        if "COUNT(*)::bigint FROM template_rows WHERE title IS NULL" in query:
            return _FakeResult([{"count": 0}])
        if "COUNT(*)::bigint FROM template_rows WHERE priority IS NULL" in query:
            return _FakeResult([{"count": 1}])
        if "COUNT(*)::bigint FROM template_rows WHERE effective_from IS NULL" in query:
            return _FakeResult([{"count": 0}])
        if "COUNT(DISTINCT title)::bigint AS distinct_count" in query:
            return _FakeResult([{"distinct_count": 2}])
        if "COUNT(DISTINCT priority)::bigint AS distinct_count" in query:
            return _FakeResult([{"distinct_count": 30}])
        if "SELECT title AS value, COUNT(*)::bigint AS hits" in query:
            return _FakeResult([{"value": "Заявка на сетевую связность", "hits": 2}, {"value": "Другая заявка", "hits": 1}])
        if "SELECT priority AS value, COUNT(*)::bigint AS hits" in query:
            return _FakeResult([{"value": 10, "hits": 5}, {"value": 20, "hits": 4}])
        if "SELECT MIN(priority) AS min_value, MAX(priority) AS max_value" in query:
            return _FakeResult([{"min_value": 1, "max_value": 100}])
        if "SELECT MIN(effective_from) AS min_value, MAX(effective_from) AS max_value" in query:
            return _FakeResult([{"min_value": "2026-01-01", "max_value": "2026-06-01"}])
        if "SELECT MIN(_created_at) AS first_created_at" in query:
            return _FakeResult([{
                "first_created_at": "2026-01-01T00:00:00+00:00",
                "last_created_at": "2026-06-10T00:00:00+00:00",
                "first_updated_at": "2026-01-02T00:00:00+00:00",
                "last_updated_at": "2026-06-11T00:00:00+00:00",
            }])
        raise AssertionError(f"Unexpected query: {query} params={params}")


@pytest.mark.asyncio
async def test_collection_info_builder_uses_runtime_resolved_operations():
    builder = build_default_collection_info_response_builder()
    collection = SimpleNamespace(
        id="col-1",
        slug="template",
        name="Template Collection",
        collection_type="template",
        status="active",
        schema_status="fresh",
        table_name="template_rows",
        last_sync_at=None,
        current_version=SimpleNamespace(
            data_description="Template rows",
            usage_purpose="Fill request forms",
            usage_rules="Find template, inspect schema, then fill.",
        ),
        is_local=True,
        entity_type=None,
        vector_fields=["body_vector"],
        get_business_fields=lambda: [
            {"name": "title", "data_type": "string", "category": "user"},
            {"name": "priority", "data_type": "integer", "category": "user"},
            {"name": "effective_from", "data_type": "date", "category": "user"},
            {"name": "payload", "data_type": "json", "category": "user"},
            {"name": "body_vector", "data_type": "text", "category": "user", "used_in_retrieval": True},
        ],
    )
    operation = ResolvedOperation.model_validate(
        {
            "operation_slug": "instance.local-template-tools.collection.template.fill",
            "operation": "collection.template.fill",
            "name": "Fill Template",
            "scope": "collection",
            "description": "Fill a template with values.",
            "input_schema": {"type": "object", "properties": {"row_id": {"type": "string"}}},
            "output_schema": None,
            "data_instance_id": "inst-1",
            "data_instance_slug": "template",
            "collection_slug": "template",
            "source": "local",
            "risk_level": "safe",
            "side_effects": False,
            "idempotent": True,
            "requires_confirmation": False,
            "credential_scope": "auto",
            "systems": [],
            "target": {
                "operation_slug": "instance.local-template-tools.collection.template.fill",
                "provider_type": "local",
                "provider_instance_id": "provider-1",
                "provider_instance_slug": "local-template-tools",
                "data_instance_id": "inst-1",
                "data_instance_slug": "template",
                "has_credentials": False,
            },
        }
    )

    operations = builder.operation_resolver.resolve_for_collection(
        runtime_deps=RuntimeDependencies(resolved_operations=[operation]),
        collection_slug="template",
        collection=collection,
    )
    payload = await builder.build(
        session=_FakeSession(),
        collection=collection,
        operations=operations,
        legacy_payload={
            "schema": {"fields": []},
            "filter_hints": {"fields": {}},
            "stats": {},
            "dimensions": {},
            "remote_catalog": {},
        },
    )

    assert payload["collection"]["usage_rules"] == "Find template, inspect schema, then fill."
    assert payload["readiness"]["status"] == "ready"
    assert payload["tools"][0]["tool_name"] == "collection.template.fill"
    assert payload["tools"][0]["invoke_as"] == "instance.local-template-tools.collection.template.fill"
    assert payload["contracts"]["workflow"]
    assert payload["runtime_enrichment"]["status"] == "ready"
    assert payload["runtime_enrichment"]["data"]["row_count"] == 3
    assert "payload" not in payload["runtime_enrichment"]["data"]["field_profiles"]
    assert "body_vector" not in payload["runtime_enrichment"]["data"]["field_profiles"]
    assert payload["runtime_enrichment"]["data"]["field_profiles"]["title"]["complete"] is True
    assert payload["runtime_enrichment"]["data"]["field_profiles"]["priority"]["truncated"] is True
    assert payload["runtime_enrichment"]["data"]["temporal_bounds"]["last_updated_at"] == "2026-06-11T00:00:00+00:00"


@pytest.mark.asyncio
async def test_collection_info_builder_builds_remote_api_metadata_enrichment():
    builder = build_default_collection_info_response_builder()
    collection = SimpleNamespace(
        id="col-2",
        slug="netbox_assets",
        name="NetBox Assets",
        collection_type="api",
        status="active",
        schema_status="fresh",
        table_name=None,
        last_sync_at=SimpleNamespace(isoformat=lambda: "2026-06-30T10:00:00+00:00"),
        current_version=SimpleNamespace(
            data_description="Remote objects",
            usage_purpose="Inspect remote inventory",
            usage_rules="Use remote objects carefully.",
        ),
        is_local=False,
        entity_type=None,
        vector_fields=[],
        table_schema={
            "entities": [
                {"entity_type": "device", "aliases": ["devices"], "examples": ["sw01"]},
                {"entity_type": "site", "aliases": ["sites"], "examples": ["dc1"]},
            ]
        },
        source_contract={"entities": [{"entity_type": "rack"}]},
        get_filterable_fields=lambda: [{"name": "name"}, {"name": "site"}],
        get_sortable_fields=lambda: [{"name": "name"}],
        get_business_fields=lambda: [],
    )

    payload = await builder.build(
        session=_FakeSession(),
        collection=collection,
        operations=[],
        legacy_payload={
            "schema": {"fields": []},
            "filter_hints": {"fields": {}},
            "stats": {},
            "dimensions": {},
            "remote_catalog": {},
        },
    )

    assert payload["runtime_enrichment"]["status"] == "ready"
    assert payload["runtime_enrichment"]["type"] == "api"
    assert payload["runtime_enrichment"]["mode"] == "metadata_only"
    assert payload["runtime_enrichment"]["data"]["entity_count"] == 3
    assert payload["runtime_enrichment"]["data"]["filterable_fields"] == ["name", "site"]
    assert payload["runtime_enrichment"]["data"]["sortable_fields"] == ["name"]
    assert payload["runtime_enrichment"]["data"]["observed_values_available"] is False
    assert payload["runtime_enrichment"]["data"]["freshness"]["last_sync_at"] == "2026-06-30T10:00:00+00:00"
    assert "stored remote API discovery metadata" in payload["runtime_enrichment"]["message"]
