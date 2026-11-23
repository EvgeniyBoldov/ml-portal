"""Unit tests for CollectionTextSearchTool (collection.template.search flow and helpers)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.collection_text_search import CollectionTextSearchTool
from app.agents.context import ToolContext
from app.agents.runtime.rerank_client import RerankClientError, RerankScoredIndex
from app.models.collection import Collection, CollectionType, FieldCategory, FieldType
from app.services.collection.row_service import CollectionRowService
from app.services.collection.vector_lifecycle import CollectionVectorLifecycleService
from app.services.collection_service import CollectionService
from app.services.vector_index_service import VectorIndexService, VectorIndexTarget


def _collection(**overrides) -> Collection:
    attrs: dict = {
        "id": uuid4(),
        "data_instance_id": uuid4(),
        "tenant_id": uuid4(),
        "collection_type": CollectionType.TABLE.value,
        "slug": "tickets",
        "name": "Tickets",
        "description": "Test collection",
        "table_name": "coll_test_tickets",
        "qdrant_collection_name": "qdrant_tickets",
        "fields": [
            {
                "name": "title",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.STRING.value,
                "required": True,
                "description": "Title",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "status",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.ENUM.value,
                "required": False,
                "description": "Status",
                "filterable": True,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "description",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.TEXT.value,
                "required": False,
                "description": "Description",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": True,
                "used_in_prompt_context": True,
            },
            {
                "name": "body",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.TEXT.value,
                "required": False,
                "description": "Body",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": True,
                "used_in_prompt_context": True,
            },
            {
                "name": "priority",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.INTEGER.value,
                "required": False,
                "description": "Priority",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "attachment",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.FILE.value,
                "required": False,
                "description": "Attachment",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
        ],
        "status": "ready",
        "total_rows": 0,
        "vectorized_rows": 0,
        "total_chunks": 0,
        "failed_rows": 0,
        "is_active": True,
        "allow_unfiltered_search": False,
        "max_limit": 100,
        "query_timeout_seconds": 10,
    }
    attrs.update(overrides)
    return Collection(**attrs)


def _target(alias: str, fingerprint: str = "fp1") -> VectorIndexTarget:
    return VectorIndexTarget(
        model_alias=alias,
        collection_name=f"vi_{alias}",
        dimensions=8,
        fingerprint=fingerprint,
        version="v1",
        embedding_service="svc",
    )


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)


class _FakeSession:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed: list[tuple[str, dict | None]] = []

    async def execute(self, clause, params=None):
        self.executed.append((str(clause), params))
        return _FakeResult(rows=self._rows)


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _norm(sql: str) -> str:
    return " ".join(sql.split())


async def _run(
    monkeypatch,
    args,
    *,
    collection=None,
    not_found=False,
    session_rows=None,
    model_aliases=None,
    targets=None,
    compat_filters=None,
    store_hits=None,
    rerank_return=None,
    rerank_side_effect=None,
    fallback_rows=None,
):
    collection = collection if collection is not None else _collection()
    session = _FakeSession(rows=session_rows)

    store = SimpleNamespace()
    store.search = (
        AsyncMock(side_effect=list(store_hits))
        if store_hits is not None
        else AsyncMock(return_value=[])
    )

    rerank = AsyncMock(return_value=[] if rerank_return is None else rerank_return)
    if rerank_side_effect is not None:
        rerank = AsyncMock(side_effect=rerank_side_effect)

    embed_calls: list[tuple[object, list[str]]] = []

    def _embed(service, texts):
        embed_calls.append((service, list(texts)))
        return [[0.1, 0.2]]

    targets = (
        targets
        if targets is not None
        else [_target("emb-v1"), _target("emb-v2", fingerprint="fp1")]
    )
    if compat_filters is None:
        compat_filters = [
            {"must": [("embed_model_alias", t.model_alias)]} if i == 0 else None
            for i, t in enumerate(targets)
        ]
    search_targets_mock = AsyncMock(
        side_effect=[
            [(f"qdrant_scope_{t.model_alias}", compat)]
            for t, compat in zip(targets, compat_filters)
        ]
    )

    monkeypatch.setattr(
        "app.core.db.get_session_factory", lambda: lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        CollectionService,
        "get_by_slug",
        AsyncMock(return_value=None if not_found else collection),
    )
    monkeypatch.setattr("app.adapters.impl.qdrant.QdrantVectorStore", lambda: store)
    monkeypatch.setattr(
        CollectionVectorLifecycleService,
        "resolve_target_vector_models",
        AsyncMock(
            return_value=["emb-v1", "emb-v2"] if model_aliases is None else model_aliases
        ),
    )
    monkeypatch.setattr(VectorIndexService, "resolve_many", AsyncMock(return_value=targets))
    monkeypatch.setattr(VectorIndexService, "search_targets", search_targets_mock)
    monkeypatch.setattr("app.services.bounded_embeddings.embed_texts_bounded", _embed)
    monkeypatch.setattr(
        "app.services.vector_rank_fusion.fuse_vector_hits", lambda hits: hits
    )
    monkeypatch.setattr("app.agents.runtime.rerank_client.rerank_scores", rerank)
    row_search = AsyncMock(return_value=fallback_rows if fallback_rows is not None else [])
    monkeypatch.setattr(CollectionRowService, "search", row_search)

    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    result = await CollectionTextSearchTool().v1_0_0(ctx, args)
    return SimpleNamespace(
        result=result,
        session=session,
        store=store,
        rerank=rerank,
        embed_calls=embed_calls,
        row_search=row_search,
        collection=collection,
    )


def _hit(point_id: str, score: float, row_id: str, field: str, text: str) -> dict:
    return {
        "id": point_id,
        "score": score,
        "payload": {"row_id": row_id, "field_name": field, "text": text},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Flow: happy path
# ─────────────────────────────────────────────────────────────────────────────


async def test_happy_path_two_targets_rerank_and_enrichment(monkeypatch):
    hits1 = [_hit("pt-1", 0.9, "rid-1", "description", "Network issue description")]
    hits2 = [_hit("pt-2", 0.6, "rid-2", "body", "body text")]
    session_rows = [
        {
            "id": "rid-2",
            "title": "Second",
            "status": "open",
            "description": "d2",
            "body": "b2",
            "priority": 2,
            "attachment": None,
        },
        {
            "id": "rid-1",
            "title": "First",
            "status": "closed",
            "description": "d1",
            "body": "b1",
            "priority": 1,
            "attachment": "file.pdf",
        },
    ]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "network issue", "limit": 10},
        session_rows=session_rows,
        store_hits=[hits1, hits2],
        rerank_return=[
            RerankScoredIndex(index=1, score=0.95),
            RerankScoredIndex(index=0, score=0.5),
        ],
    )

    result = run.result
    assert result.success is True
    data = result.data
    assert data["total"] == 2
    assert data["collection"] == "tickets"
    assert data["vector_fields"] == ["description", "body"]

    hits = data["hits"]
    assert [h["row_id"] for h in hits] == ["rid-2", "rid-1"]
    assert hits[0]["score"] == 0.95
    assert hits[0]["primary_field"] == "body"
    assert hits[0]["primary_fragment"] == "body text"
    assert hits[0]["matched_fields"] == ["body"]
    assert hits[0]["matched_fragments"] == ["body text"]
    assert hits[1]["score"] == 0.5
    assert hits[1]["primary_field"] == "description"
    assert hits[1]["matched_fragments"] == ["Network issue description"]

    # rerank receives fragments in vector order
    run.rerank.assert_awaited_once()
    kwargs = run.rerank.await_args.kwargs
    assert kwargs["documents"] == ["Network issue description", "body text"]
    assert kwargs["query"] == "network issue"
    assert kwargs["top_k"] == 2

    # both targets share a fingerprint → single embedding call (cached)
    assert len(run.embed_calls) == 1
    assert run.embed_calls[0][1] == ["network issue"]

    # qdrant searched per scoped collection with merged filters
    assert run.store.search.await_count == 2
    first, second = run.store.search.await_args_list
    assert first.kwargs["collection"] == "qdrant_scope_emb-v1"
    assert first.kwargs["query"] == [0.1, 0.2]
    assert first.kwargs["top_k"] == 20
    assert first.kwargs["filter"] == {"must": [("embed_model_alias", "emb-v1")]}
    assert second.kwargs["collection"] == "qdrant_scope_emb-v2"
    assert second.kwargs["filter"] is None

    # payload enrichment mutates store hits in place
    assert hits1[0]["payload"]["embed_model_alias"] == "emb-v1"
    assert hits1[0]["payload"]["qdrant_collection_name"] == "qdrant_scope_emb-v1"
    assert hits2[0]["payload"]["embed_model_alias"] == "emb-v2"
    assert hits2[0]["payload"]["qdrant_collection_name"] == "qdrant_scope_emb-v2"

    # full-row SQL uses post-rerank id order
    sql, params = run.session.executed[0]
    assert _norm(sql) == (
        "SELECT * FROM coll_test_tickets WHERE id::text IN (:rid_0, :rid_1)"
    )
    assert params == {"rid_0": "rid-2", "rid_1": "rid-1"}

    # row_data skips file fields and None values
    assert hits[0]["row_data"] == {
        "title": "Second",
        "status": "open",
        "description": "d2",
        "body": "b2",
        "priority": 2,
    }
    assert hits[1]["row_data"] == {
        "title": "First",
        "status": "closed",
        "description": "d1",
        "body": "b1",
        "priority": 1,
    }


async def test_vector_order_preserved_when_rerank_returns_empty(monkeypatch):
    hits1 = [_hit("pt-1", 0.9, "rid-1", "description", "d text")]
    hits2 = [_hit("pt-2", 0.6, "rid-2", "body", "b text")]
    session_rows = [
        {"id": "rid-1", "title": "First"},
        {"id": "rid-2", "title": "Second"},
    ]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        session_rows=session_rows,
        store_hits=[hits1, hits2],
    )
    assert run.result.success is True
    hits = run.result.data["hits"]
    assert [h["row_id"] for h in hits] == ["rid-1", "rid-2"]
    assert [h["score"] for h in hits] == [0.9, 0.6]


async def test_vector_order_preserved_when_rerank_fails(monkeypatch):
    hits1 = [_hit("pt-1", 0.9, "rid-1", "description", "d text")]
    session_rows = [{"id": "rid-1", "title": "First"}]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        session_rows=session_rows,
        targets=[_target("emb-v1")],
        compat_filters=[None],
        store_hits=[hits1],
        rerank_side_effect=RerankClientError("down"),
    )
    assert run.result.success is True
    hits = run.result.data["hits"]
    assert [h["row_id"] for h in hits] == ["rid-1"]
    assert hits[0]["score"] == 0.9
    run.rerank.assert_awaited_once()


async def test_empty_primary_fragment_falls_back_to_first_matched_fragment(monkeypatch):
    hits = [
        _hit("pt-a", 0.9, "r1", "description", ""),
        _hit("pt-b", 0.5, "r1", "body", "body fragment"),
    ]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        session_rows=[{"id": "r1", "title": "T", "status": "open"}],
        targets=[_target("emb-v1")],
        compat_filters=[None],
        store_hits=[hits],
    )
    assert run.result.success is True
    hit = run.result.data["hits"][0]
    assert hit["primary_field"] == "description"
    assert hit["primary_fragment"] == ""
    assert hit["matched_fields"] == ["body", "description"]
    assert hit["matched_fragments"] == ["body fragment"]
    assert run.rerank.await_args.kwargs["documents"] == ["body fragment"]


async def test_fragment_trimming_dedupe_and_cap(monkeypatch):
    long_a = "A" * 600
    frag_b = "B" * 300
    frag_c = "C" * 80
    frag_d = "D" * 80
    hits = [
        _hit("p1", 0.9, "r1", "description", long_a),
        _hit("p2", 0.8, "r1", "body", frag_b),
        _hit("p3", 0.7, "r1", "body", frag_c),
        _hit("p4", 0.6, "r1", "body", frag_c),  # duplicate fragment
        _hit("p5", 0.5, "r1", "body", frag_d),  # beyond the cap of 3
    ]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        session_rows=[{"id": "r1", "title": "T"}],
        targets=[_target("emb-v1")],
        compat_filters=[None],
        store_hits=[hits],
    )
    assert run.result.success is True
    hit = run.result.data["hits"][0]
    assert hit["primary_fragment"] == "A" * 497 + "..."
    assert len(hit["primary_fragment"]) == 500
    fragments = hit["matched_fragments"]
    assert fragments == ["A" * 217 + "...", "B" * 217 + "...", frag_c]


async def test_stale_row_ids_skipped(monkeypatch):
    hits = [
        _hit("pt-1", 0.95, "rid-gone", "description", "gone"),
        _hit("pt-2", 0.9, "rid-1", "description", "kept"),
    ]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        session_rows=[{"id": "rid-1", "title": "First"}],
        targets=[_target("emb-v1")],
        compat_filters=[None],
        store_hits=[hits],
    )
    assert run.result.success is True
    data = run.result.data
    assert data["total"] == 1
    assert [h["row_id"] for h in data["hits"]] == ["rid-1"]
    sql, params = run.session.executed[0]
    assert params == {"rid_0": "rid-gone", "rid_1": "rid-1"}


async def test_hits_without_row_id_are_skipped(monkeypatch):
    hits = [
        {"id": "pt-1", "score": 0.9, "payload": {"field_name": "description", "text": "no row"}},
    ]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        targets=[_target("emb-v1")],
        compat_filters=[None],
        store_hits=[hits],
    )
    assert run.result.success is True
    data = run.result.data
    assert data["hits"] == []
    assert data["total"] == 0
    run.rerank.assert_not_awaited()
    run.row_search.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# Flow: keyword fallback
# ─────────────────────────────────────────────────────────────────────────────


async def test_fallback_when_not_vectorized_yet(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "network issue"},
        targets=[],
        fallback_rows=[{"id": "r1", "title": "Network issue", "description": None}],
    )
    result = run.result
    assert result.success is True
    data = result.data
    assert data["total"] == 1
    assert data["vector_fields"] == ["description", "body"]
    hit = data["hits"][0]
    assert hit["row_id"] == "r1"
    assert hit["score"] == 7.5
    assert hit["matched_fields"] == ["title"]
    assert hit["primary_fragment"] == "Network issue"
    assert hit["row_data"] == {"title": "Network issue"}
    assert result.metadata["message"] == (
        "Collection exists but has not been vectorized yet. Returned fallback lexical matches."
    )
    run.store.search.assert_not_awaited()
    run.row_search.assert_awaited_once()
    assert run.row_search.await_args.args == (run.collection,)
    assert run.row_search.await_args.kwargs == {"limit": 100, "offset": 0, "query": None}


async def test_fallback_when_not_vectorized_yet_empty(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "network issue"},
        targets=[],
        fallback_rows=[],
    )
    assert run.result.success is True
    assert run.result.data["hits"] == []
    assert run.result.metadata["message"] == (
        "Collection exists but has not been vectorized yet."
    )


async def test_fallback_when_no_vector_hits(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "network issue"},
        store_hits=[[], []],
        fallback_rows=[{"id": "r1", "title": "Network issue"}],
    )
    result = run.result
    assert result.success is True
    assert result.data["hits"][0]["row_id"] == "r1"
    assert result.metadata["message"] == "No vector hits; returned fallback lexical matches."
    run.row_search.assert_awaited_once()


async def test_fallback_when_no_vector_hits_empty_message_none(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "network issue"},
        store_hits=[[], []],
        fallback_rows=[],
    )
    assert run.result.success is True
    assert run.result.data["hits"] == []
    assert run.result.metadata["message"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Flow: argument handling
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "limit_value,expected_top_k",
    [("abc", 20), (100, 100), (5, 10)],
    ids=["invalid-limit", "capped-at-50", "plain-limit"],
)
async def test_limit_parsing_controls_top_k(monkeypatch, limit_value, expected_top_k):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q", "limit": limit_value},
        targets=[_target("emb-v1")],
        compat_filters=[None],
        store_hits=[[]],
    )
    assert run.result.success is True
    run.store.search.assert_awaited_once()
    assert run.store.search.await_args.kwargs["top_k"] == expected_top_k


async def test_field_and_payload_filters_merged_into_qdrant_filter(monkeypatch):
    run = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "query": "q",
            "field_name": "description",
            "filters": {"status": "open"},
        },
        targets=[_target("emb-v1")],
        compat_filters=[None],
        store_hits=[[ _hit("pt-1", 0.9, "rid-1", "description", "d") ]],
        session_rows=[{"id": "rid-1", "title": "First"}],
    )
    assert run.result.success is True
    run.store.search.assert_awaited_once()
    assert run.store.search.await_args.kwargs["filter"] == {
        "must": [("field_name", "description"), ("status", "open")]
    }


# ─────────────────────────────────────────────────────────────────────────────
# Flow: failure branches
# ─────────────────────────────────────────────────────────────────────────────


async def test_collection_not_found(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        not_found=True,
    )
    assert run.result.success is False
    assert run.result.error == "Collection 'tickets' not found"


async def test_collection_slug_mismatch(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        collection=_collection(slug="other"),
    )
    assert run.result.success is False
    assert run.result.error == "Collection slug mismatch: expected 'tickets', got 'other'"


async def test_collection_without_vector_search(monkeypatch):
    collection = _collection()
    collection.fields = [
        dict(f, used_in_retrieval=False) for f in collection.fields
    ]
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        collection=collection,
    )
    assert run.result.success is False
    assert run.result.error == (
        "Collection 'tickets' does not have vector search enabled. "
        "Mark at least one text field with used_in_retrieval=true to enable it."
    )


async def test_collection_without_qdrant_name(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        collection=_collection(qdrant_collection_name=None),
    )
    assert run.result.success is False
    assert run.result.error == "Collection 'tickets' has no Qdrant collection configured."


async def test_field_not_vector_enabled(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q", "field_name": "title"},
    )
    assert run.result.success is False
    assert run.result.error == (
        "Field 'title' is not vector-enabled. Available vector fields: description, body"
    )


async def test_no_embedding_models(monkeypatch):
    run = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "query": "q"},
        model_aliases=[],
    )
    assert run.result.success is False
    assert run.result.error == "Cannot determine embedding model for this collection."


async def test_unhandled_exception_wrapped(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(
        "app.core.db.get_session_factory", lambda: lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        CollectionService, "get_by_slug", AsyncMock(side_effect=RuntimeError("boom"))
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    result = await CollectionTextSearchTool().v1_0_0(
        ctx, {"collection_slug": "tickets", "query": "q"}
    )
    assert result.success is False
    assert result.error == "Search failed: boom"


# ─────────────────────────────────────────────────────────────────────────────
# Direct: _fetch_full_rows
# ─────────────────────────────────────────────────────────────────────────────


async def test_fetch_full_rows_empty_ids_returns_empty():
    tool = CollectionTextSearchTool()
    session = _FakeSession()
    assert await tool._fetch_full_rows(session, _collection(), []) == {}
    assert session.executed == []


async def test_fetch_full_rows_without_table_name_returns_empty():
    tool = CollectionTextSearchTool()
    session = _FakeSession()
    assert await tool._fetch_full_rows(session, _collection(table_name=None), ["a"]) == {}
    assert session.executed == []


async def test_fetch_full_rows_maps_rows_by_id():
    tool = CollectionTextSearchTool()
    rows = [
        {"id": "a", "title": "First", "attachment": "f.pdf", "priority": None},
        {"id": "b", "title": "Second", "status": "open"},
    ]
    session = _FakeSession(rows=rows)
    result = await tool._fetch_full_rows(session, _collection(), ["a", "b"])
    assert result == {
        "a": {"title": "First"},
        "b": {"title": "Second", "status": "open"},
    }
    sql, params = session.executed[0]
    assert _norm(sql) == (
        "SELECT * FROM coll_test_tickets WHERE id::text IN (:rid_0, :rid_1)"
    )
    assert params == {"rid_0": "a", "rid_1": "b"}


# ─────────────────────────────────────────────────────────────────────────────
# Direct: serialization helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_serialize_scalar_cases():
    tool = CollectionTextSearchTool()
    value_uuid = uuid4()
    plain = object()
    assert tool._serialize_scalar(value_uuid) == str(value_uuid)
    assert tool._serialize_scalar(Decimal("1.25")) == 1.25
    assert tool._serialize_scalar(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05"
    assert tool._serialize_scalar(date(2026, 1, 2)) == "2026-01-02"
    assert tool._serialize_scalar("x" * 600) == "x" * 497 + "..."
    assert tool._serialize_scalar(["a", Decimal("2")]) == ["a", 2.0]
    assert tool._serialize_scalar((1, 2)) == [1, 2]
    assert tool._serialize_scalar({"k": Decimal("2"), 5: "v"}) == {"k": 2.0, "5": "v"}
    assert tool._serialize_scalar(7) == 7
    assert tool._serialize_scalar(1.5) == 1.5
    assert tool._serialize_scalar(True) is True
    assert tool._serialize_scalar(None) is None
    assert tool._serialize_scalar(plain) == str(plain)


def test_serialize_row_payload_skips_none_and_file_fields():
    tool = CollectionTextSearchTool()
    row = {
        "title": None,
        "status": "open",
        "description": "d",
        "body": None,
        "priority": 3,
        "attachment": "f.pdf",
    }
    assert tool._serialize_row_payload(_collection(), row) == {
        "status": "open",
        "description": "d",
        "priority": 3,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Direct: _fallback_keyword_hits (non-basic branches)
# ─────────────────────────────────────────────────────────────────────────────


async def test_fallback_keyword_hits_punctuation_only_query(monkeypatch):
    row_search = AsyncMock(return_value=[{"id": "r1", "title": "Network"}])
    monkeypatch.setattr(CollectionRowService, "search", row_search)
    tool = CollectionTextSearchTool()
    hits = await tool._fallback_keyword_hits(
        session=_FakeSession(),
        collection=_collection(),
        query="!!!",
        limit=5,
        vector_fields=["description", "body"],
    )
    assert hits == []
    row_search.assert_awaited_once()


async def test_fallback_keyword_hits_empty_rows(monkeypatch):
    monkeypatch.setattr(CollectionRowService, "search", AsyncMock(return_value=[]))
    tool = CollectionTextSearchTool()
    hits = await tool._fallback_keyword_hits(
        session=_FakeSession(),
        collection=_collection(),
        query="network issue",
        limit=5,
        vector_fields=["description", "body"],
    )
    assert hits == []


async def test_fallback_keyword_hits_scoring_ordering_and_limit(monkeypatch):
    rows = [
        {"id": 1, "title": "Network issue down", "description": "network"},
        {
            "id": 2,
            "title": None,
            "description": "Network maintenance planned, no issue here",
        },
        {"id": 3, "semantic_description": "issue with routing"},
        {"id": 4, "title": "unrelated", "priority": 5},
        {"id": 5, "body": "network outage issue"},
    ]
    row_search = AsyncMock(return_value=rows)
    monkeypatch.setattr(CollectionRowService, "search", row_search)
    tool = CollectionTextSearchTool()
    collection = _collection()
    hits = await tool._fallback_keyword_hits(
        session=_FakeSession(),
        collection=collection,
        query="network issue",
        limit=4,
        vector_fields=["description", "body"],
    )

    assert [h["row_id"] for h in hits] == ["1", "2", "3", "5"]
    # substring + full token overlap + title bonus
    assert hits[0]["score"] == 7.5
    assert hits[0]["matched_fields"] == ["title"]
    assert hits[0]["primary_field"] == "title"
    assert hits[0]["primary_fragment"] == "Network issue down"
    # token overlap + description bonus
    assert hits[1]["score"] == 2.0
    assert hits[1]["matched_fields"] == ["description"]
    # partial overlap + semantic_description bonus
    assert hits[2]["score"] == 1.3
    assert hits[2]["matched_fields"] == ["semantic_description"]
    # vector field match: overlap only, no field bonus
    assert hits[3]["score"] == 1.0
    assert hits[3]["matched_fields"] == ["body"]

    assert row_search.await_args.args == (collection,)
    assert row_search.await_args.kwargs == {"limit": 50, "offset": 0, "query": None}
