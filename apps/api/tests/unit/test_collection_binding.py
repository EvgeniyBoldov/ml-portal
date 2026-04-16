from app.services.collection_binding import (
    resolve_collection_runtime_domain,
)


def test_runtime_domain_prefers_collection_type_table():
    domain = resolve_collection_runtime_domain(
        {
            "binding_type": "collection_asset",
            "collection_id": "4de4351e-5d96-4016-b7d0-05a2a6bfdd6d",
            "collection_type": "table",
        },
        fallback_domain="rag",
    )
    assert domain == "collection.table"


def test_runtime_domain_prefers_collection_type_document():
    domain = resolve_collection_runtime_domain(
        {
            "binding_type": "collection_asset",
            "collection_id": "4de4351e-5d96-4016-b7d0-05a2a6bfdd6d",
            "collection_type": "document",
        },
        fallback_domain="rag",
    )
    assert domain == "collection.document"


def test_runtime_domain_prefers_collection_type_sql():
    domain = resolve_collection_runtime_domain(
        {
            "binding_type": "collection_asset",
            "collection_id": "4de4351e-5d96-4016-b7d0-05a2a6bfdd6d",
            "collection_type": "sql",
        },
        fallback_domain="sql",
    )
    assert domain == "collection.sql"


def test_runtime_domain_prefers_collection_type_api():
    domain = resolve_collection_runtime_domain(
        {
            "binding_type": "collection_asset",
            "collection_id": "4de4351e-5d96-4016-b7d0-05a2a6bfdd6d",
            "collection_type": "api",
        },
        fallback_domain="api",
    )
    assert domain == "collection.api"


def test_runtime_domain_falls_back_when_not_collection_bound():
    domain = resolve_collection_runtime_domain(
        {"provider_kind": "local"},
        fallback_domain="sql",
    )
    assert domain == "sql"


def test_runtime_domain_falls_back_when_collection_type_unknown():
    domain = resolve_collection_runtime_domain(
        {
            "binding_type": "collection_asset",
            "collection_id": "4de4351e-5d96-4016-b7d0-05a2a6bfdd6d",
            "collection_type": "netbox",
        },
        fallback_domain="collection.table",
    )
    assert domain == "collection.table"
