from types import SimpleNamespace

from app.services.collection_tool_resolver import CollectionToolResolver


def _instance(*, config=None, domain=""):
    return SimpleNamespace(config=config or {}, domain=domain)


def test_resolve_local_domains_prefers_collection_binding_type():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_id": "3b59e0a0-a1d4-4b8d-a4f2-7cdb9de9f35a",
            "collection_type": "table",
        },
        domain="rag",
    )

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["collection.table", "rag"]


def test_resolve_local_domains_avoids_duplicates():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_slug": "kb_docs",
            "tenant_id": "58e616fc-acb8-49bb-8655-7f26f1f0fcb4",
            "collection_type": "document",
        },
        domain="collection.document",
    )

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["collection.document"]


def test_resolve_local_domains_falls_back_to_instance_domain():
    instance = _instance(
        config={"provider_kind": "local"},
        domain="sql",
    )

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["sql"]


def test_catalog_tool_supported_for_bound_document_collection():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_type": "document",
        },
        domain="collection.document",
    )
    tool = SimpleNamespace(source="local", slug="collection.catalog")
    bound_collection = SimpleNamespace(id="any")

    supported = CollectionToolResolver._is_tool_supported_for_instance(
        tool=tool,
        instance=instance,
        bound_collection=bound_collection,
    )

    assert supported is True


def test_catalog_tool_supported_for_bound_api_collection():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_type": "api",
        },
        domain="collection.api",
    )
    tool = SimpleNamespace(source="local", slug="collection.catalog")
    bound_collection = SimpleNamespace(id="any")

    supported = CollectionToolResolver._is_tool_supported_for_instance(
        tool=tool,
        instance=instance,
        bound_collection=bound_collection,
    )

    assert supported is True
