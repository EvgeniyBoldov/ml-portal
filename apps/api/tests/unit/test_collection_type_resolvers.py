from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.agents.collection_resolvers.local_document import LocalDocumentCollectionResolver
from app.agents.collection_resolvers.local_table import LocalTableCollectionResolver
from app.agents.collection_resolvers.remote_api import RemoteApiCollectionResolver
from app.agents.collection_resolvers.remote_sql import RemoteSqlCollectionResolver
from app.agents.collection_resolvers.router import CollectionResolverRouter


class _FakeCollection:
    def __init__(self, collection_type: str, *, with_version: bool = True):
        self.id = uuid4()
        self.collection_type = collection_type
        self.slug = f"{collection_type}-coll"
        self.name = f"{collection_type} collection"
        self.description = None
        self.status = "ready"
        self.table_name = "public.devices"
        self.table_schema = {"columns": [{"name": "id", "type": "uuid"}]}
        self.last_sync_at = None
        self.vector_fields = ["content"]
        self.current_version = (
            SimpleNamespace(
                version=3,
                semantic_profile={"summary": "", "entity_types": [], "examples": []},
                policy_hints={"dos": ["respect filters"]},
            )
            if with_version
            else None
        )

    @staticmethod
    def get_user_fields():
        return [{"name": "title", "category": "user", "data_type": "text", "required": False}]

    @staticmethod
    def get_specific_fields():
        return [{"name": "source_id", "category": "specific", "data_type": "string", "required": False}]

    @staticmethod
    def get_system_fields():
        return [{"name": "id", "category": "system", "data_type": "string", "required": True}]

    @staticmethod
    def get_filterable_fields():
        return [{"name": "title"}]

    @staticmethod
    def get_sortable_fields():
        return [{"name": "title"}]

    @staticmethod
    def get_prompt_context_fields():
        return [{"name": "title"}]


def _fake_instance(domain: str = "collection.table"):
    return SimpleNamespace(domain=domain, slug="inst-1", config={})


def test_local_table_resolver_defaults():
    resolver = LocalTableCollectionResolver()
    profile = resolver.build(instance=_fake_instance("collection.table"), collection=_FakeCollection("table"))
    assert profile.entity_types == ["record"]
    assert profile.schema_hints["collection_type"] == "table"
    assert "structured search" in (profile.use_cases or "")


def test_local_document_resolver_defaults():
    resolver = LocalDocumentCollectionResolver()
    profile = resolver.build(instance=_fake_instance("collection.document"), collection=_FakeCollection("document"))
    assert profile.entity_types == ["document"]
    assert profile.schema_hints["collection_type"] == "document"
    assert "semantic lookup" in (profile.use_cases or "")


def test_remote_sql_resolver_defaults():
    resolver = RemoteSqlCollectionResolver()
    profile = resolver.build(instance=_fake_instance("sql"), collection=_FakeCollection("sql"))
    assert profile.entity_types == ["remote_table", "remote_schema_object"]
    assert profile.schema_hints["collection_type"] == "sql"
    assert profile.schema_hints["table_name"] == "public.devices"


def test_router_dispatches_by_collection_type():
    router = CollectionResolverRouter(
        session=SimpleNamespace(),
        resolvers=[
            LocalTableCollectionResolver(),
            LocalDocumentCollectionResolver(),
            RemoteSqlCollectionResolver(),
            RemoteApiCollectionResolver(),
        ],
    )
    sql_profile = router.build(instance=_fake_instance("sql"), collection=_FakeCollection("sql"))
    api_profile = router.build(instance=_fake_instance("api"), collection=_FakeCollection("api"))
    doc_profile = router.build(
        instance=_fake_instance("collection.document"),
        collection=_FakeCollection("document"),
    )
    assert sql_profile.schema_hints["collection_type"] == "sql"
    assert api_profile.schema_hints["collection_type"] == "api"
    assert doc_profile.schema_hints["collection_type"] == "document"


def test_router_raises_for_unsupported_collection_type():
    router = CollectionResolverRouter(
        session=SimpleNamespace(),
        resolvers=[
            LocalTableCollectionResolver(),
            LocalDocumentCollectionResolver(),
            RemoteSqlCollectionResolver(),
            RemoteApiCollectionResolver(),
        ],
    )
    unknown = _FakeCollection("rag")
    try:
        router.build(instance=_fake_instance("api"), collection=unknown)
        assert False, "expected ValueError for unsupported collection_type"
    except ValueError as exc:
        assert "Unsupported collection_type" in str(exc)
