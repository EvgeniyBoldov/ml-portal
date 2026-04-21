from types import SimpleNamespace

from app.services.collection_linking import (
    context_domain_for_collection,
    runtime_domain_for_collection,
)


def _collection(collection_type: str):
    return SimpleNamespace(collection_type=collection_type)


def test_runtime_domain_maps_known_collection_types():
    assert runtime_domain_for_collection(collection=_collection("table"), fallback_domain="rag") == "collection.table"
    assert runtime_domain_for_collection(collection=_collection("document"), fallback_domain="rag") == "collection.document"
    assert runtime_domain_for_collection(collection=_collection("sql"), fallback_domain="rag") == "collection.sql"
    assert runtime_domain_for_collection(collection=_collection("api"), fallback_domain="rag") == "collection.api"


def test_runtime_domain_falls_back_for_missing_or_unknown_collection():
    assert runtime_domain_for_collection(collection=None, fallback_domain="sql") == "sql"
    assert runtime_domain_for_collection(collection=_collection("netbox"), fallback_domain="collection.table") == "collection.table"


def test_context_domain_returns_only_collection_specific_domain():
    assert context_domain_for_collection(_collection("table")) == "collection.table"
    assert context_domain_for_collection(_collection("document")) == "collection.document"
    assert context_domain_for_collection(_collection("unknown")) is None
    assert context_domain_for_collection(None) is None
