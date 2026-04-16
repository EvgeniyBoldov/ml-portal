from __future__ import annotations

from app.agents.operation_publication import (
    build_runtime_operation_slug,
    canonical_operation_identity,
    canonical_operation_name,
    resolve_publication,
)


def test_collection_table_operation_canonicalization():
    assert canonical_operation_name("collection.table", "collection.search") == "collection.table.search"
    assert canonical_operation_name("collection.table", "collection.text_search") == "collection.text_search"
    assert (
        canonical_operation_name("collection.table", "collection.aggregate")
        == "collection.table.aggregate"
    )
    assert canonical_operation_name("collection.table", "collection.get") == "collection.table.get"
    assert (
        canonical_operation_name("collection.table", "collection.catalog")
        == "collection.table.catalog_inspect"
    )


def test_collection_document_operation_canonicalization():
    assert (
        canonical_operation_name("collection.document", "collection.doc_search")
        == "collection.document.search"
    )
    assert (
        canonical_operation_name("collection.document", "collection.catalog")
        == "collection.document.catalog_inspect"
    )


def test_collection_sql_catalog_operation_canonicalization():
    assert (
        canonical_operation_name("collection.sql", "collection.catalog")
        == "collection.sql.catalog_inspect"
    )


def test_collection_api_catalog_operation_canonicalization():
    assert (
        canonical_operation_name("collection.api", "collection.catalog")
        == "collection.api.catalog_inspect"
    )


def test_canonicalization_fallback_for_unknown_domains():
    assert canonical_operation_name("jira", "jira.issue.get") == "jira.issue.get"
    assert canonical_operation_name("netbox", "netbox_get_objects") == "netbox.get_objects"


def test_collection_domain_unknown_raw_tool_is_not_published():
    assert resolve_publication(instance_domain="collection.table", raw_slug="collection.unknown") is None


def test_collection_table_semantic_tool_is_internal_not_published():
    assert resolve_publication(instance_domain="collection.table", raw_slug="collection.text_search") is None


def test_non_collection_domain_unknown_prefix_is_not_published():
    assert resolve_publication(instance_domain="jira", raw_slug="netbox.search") is None


def test_publication_prefers_discovered_domains_over_fallback_domain():
    decision = resolve_publication(
        instance_domain="rag",
        raw_slug="collection.search",
        discovered_domains=["collection.table"],
    )

    assert decision is not None
    assert decision.canonical_op_slug == "collection.table.search"


def test_collection_context_without_rule_is_not_published_even_with_non_collection_fallback():
    decision = resolve_publication(
        instance_domain="jira",
        raw_slug="collection.unknown",
        discovered_domains=["collection.table"],
    )

    assert decision is None


def test_runtime_operation_slug_builder():
    assert (
        build_runtime_operation_slug("collection-contracts", "collection.table.search")
        == "instance.collection-contracts.collection.table.search"
    )


def test_canonical_identity_returns_name_and_runtime_slug():
    canonical_name, runtime_slug = canonical_operation_identity(
        instance_slug="collection-contracts",
        instance_domain="collection.document",
        raw_slug="collection.doc_search",
    )
    assert canonical_name == "collection.document.search"
    assert runtime_slug == "instance.collection-contracts.collection.document.search"
