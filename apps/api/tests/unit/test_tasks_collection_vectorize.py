"""Unit tests for app/workers/tasks_collection_vectorize.py."""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.services.vector_index_service import VectorIndexTarget
from app.workers import tasks_collection_vectorize as vectorize_tasks

COLLECTION_ID = "11111111-1111-1111-1111-111111111111"
TENANT_ID = "22222222-2222-2222-2222-222222222222"
ROW_ID = "33333333-3333-3333-3333-333333333333"
ROW_ID_2 = "44444444-4444-4444-4444-444444444444"
TABLE_NAME = "coll_123"


class FakeResult:
    """Mimics the async SQLAlchemy result surface used by the task."""

    def __init__(self, rows=(), scalar=None):
        self._rows = list(rows)
        self._scalar = scalar
        self.rowcount = 0

    def mappings(self):
        rows = self._rows
        return SimpleNamespace(
            all=lambda: list(rows),
            first=lambda: rows[0] if rows else None,
            one=lambda: rows[0] if rows else None,
        )

    def scalar(self):
        return self._scalar


class FakeSession:
    """Routes text() statements by SQL substring because per-row loops vary call order."""

    def __init__(self):
        self.lock_acquired = True
        self.unlock_error: Exception | None = None
        self.pending_rows: list[dict] = []
        self.stats = {"vectorized_rows": 0, "failed_rows": 0, "total_chunks": 0}
        self.remaining = 0
        self.row_meta: dict | None = None
        self.executed: list[str] = []
        self.params: list[dict] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, stmt, params=None):
        sql = stmt.text
        self.executed.append(sql)
        self.params.append(params if params is not None else {})
        if "pg_try_advisory_lock" in sql:
            return FakeResult(scalar=self.lock_acquired)
        if "pg_advisory_unlock" in sql:
            if self.unlock_error is not None:
                raise self.unlock_error
            return FakeResult(scalar=True)
        if "COUNT(*) FILTER" in sql:
            return FakeResult(rows=[self.stats])
        if "SELECT COUNT(*) FROM" in sql:
            return FakeResult(scalar=self.remaining)
        if "LIMIT :lim" in sql:
            return FakeResult(rows=self.pending_rows)
        if "_vector_status, _vector_error, _vector_chunk_count" in sql:
            return FakeResult(rows=[self.row_meta] if self.row_meta is not None else [])
        return FakeResult()

    def executed_with(self, *fragments):
        """Return params of executed statements containing all fragments."""
        return [
            params
            for sql, params in zip(self.executed, self.params)
            if all(fragment in sql for fragment in fragments)
        ]


def make_session_scope(session):
    @asynccontextmanager
    async def scope():
        yield session

    return scope


def make_collection(**overrides):
    base = dict(
        id=COLLECTION_ID,
        tenant_id=TENANT_ID,
        collection_type="table",
        table_name=TABLE_NAME,
        fields=[{"name": "body", "data_type": "text", "used_in_retrieval": True}],
        qdrant_collection_name=TABLE_NAME,
        vector_config=None,
        vectorized_rows=0,
        total_chunks=0,
        failed_rows=0,
        has_vector_search=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_targets(*aliases):
    return [
        VectorIndexTarget(
            model_alias=alias,
            collection_name=TABLE_NAME if alias == "emb-default" else f"{TABLE_NAME}__{alias}",
            dimensions=8,
            fingerprint=f"fp-{alias}",
            version="v1",
            legacy_fingerprint=None,
            embedding_service=SimpleNamespace(name=alias),
        )
        for alias in aliases
    ]


def fake_embed(_service, texts):
    return [[0.5] * 8 for _ in texts]


class FakeQdrantVectorStore:
    def __init__(self):
        self.ensure_collection = AsyncMock()
        self.delete_by_filter = AsyncMock()
        self.upsert = AsyncMock()


def make_collection_service(collection):
    synced: list[tuple] = []

    class FakeCollectionService:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _collection_id):
            return collection

        async def sync_collection_status(self, coll, persist=False):
            synced.append((coll, persist))

    return FakeCollectionService, synced


def make_lifecycle_service(aliases):
    class FakeLifecycleService:
        def __init__(self, _session):
            pass

        async def resolve_target_vector_models(self, _tenant_id):
            return list(aliases)

    return FakeLifecycleService


def make_vector_index_service(targets):
    class FakeVectorIndexService:
        def __init__(self, _session):
            pass

        async def resolve_many(self, _base, _aliases):
            return list(targets)

    return FakeVectorIndexService


def wire_vectorize(monkeypatch, session, collection, *, aliases=("emb-default",)):
    """Patch every local import of vectorize_collection_rows._execute."""
    targets = make_targets(*aliases)
    store = FakeQdrantVectorStore()
    collection_service, synced = make_collection_service(collection)
    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr("app.adapters.impl.qdrant.QdrantVectorStore", lambda: store)
    monkeypatch.setattr("app.services.collection_service.CollectionService", collection_service)
    monkeypatch.setattr(
        "app.services.collection.vector_lifecycle.CollectionVectorLifecycleService",
        make_lifecycle_service(list(aliases)),
    )
    monkeypatch.setattr(
        "app.services.vector_index_service.VectorIndexService",
        make_vector_index_service(targets),
    )
    monkeypatch.setattr("app.services.bounded_embeddings.embed_texts_bounded", fake_embed)
    return store, synced


def matching_vector_config(*aliases):
    return {
        "embed_model_aliases": list(aliases),
        "index_fingerprints": {alias: f"fp-{alias}" for alias in aliases},
    }


def test_serialize_template_nodes_converts_datetimes_to_isoformat():
    node = SimpleNamespace(
        node_key="retrieval",
        status="processing",
        error_short=None,
        metrics_json={"chunks": 3},
        started_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc),
    )
    [serialized] = vectorize_tasks._serialize_template_nodes([node])
    assert serialized == {
        "node_key": "retrieval",
        "status": "processing",
        "error_short": None,
        "metrics_json": {"chunks": 3},
        "started_at": "2026-01-02T03:04:05+00:00",
        "finished_at": "2026-01-02T03:05:00+00:00",
    }


def test_serialize_template_nodes_tolerates_missing_timestamp_attributes():
    node = SimpleNamespace(node_key="retrieval", status="failed", error_short="boom", metrics_json=None)
    [serialized] = vectorize_tasks._serialize_template_nodes([node])
    assert serialized["started_at"] is None
    assert serialized["finished_at"] is None
    assert serialized["error_short"] == "boom"
    assert vectorize_tasks._serialize_template_nodes([]) == []


def test_build_point_id_is_deterministic_and_scoped_per_field_and_chunk():
    expected = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{COLLECTION_ID}:{ROW_ID}:body:0"))
    point_id = vectorize_tasks._build_point_id(COLLECTION_ID, ROW_ID, "body", 0)
    assert point_id == expected
    assert point_id == vectorize_tasks._build_point_id(COLLECTION_ID, ROW_ID, "body", 0)
    assert vectorize_tasks._build_point_id(COLLECTION_ID, ROW_ID, "title", 0) != point_id
    assert vectorize_tasks._build_point_id(COLLECTION_ID, ROW_ID, "body", 1) != point_id
    assert vectorize_tasks._build_point_id(COLLECTION_ID, ROW_ID_2, "body", 0) != point_id


def test_collection_lock_key_is_stable_and_within_advisory_range():
    key = vectorize_tasks._collection_lock_key(COLLECTION_ID)
    assert isinstance(key, int)
    assert 0 <= key <= 2**63 - 2
    assert key == vectorize_tasks._collection_lock_key(COLLECTION_ID)
    assert vectorize_tasks._collection_lock_key(ROW_ID) != key


def test_resolve_chunk_config_falls_back_to_defaults_on_invalid_values():
    assert vectorize_tasks._resolve_chunk_config({"chunk_size": "not-an-int", "overlap": "wide"}) == (
        vectorize_tasks.DEFAULT_CHUNK_SIZE,
        vectorize_tasks.DEFAULT_CHUNK_OVERLAP,
    )
    assert vectorize_tasks._resolve_chunk_config({"chunk_size": None, "overlap": None}) == (
        vectorize_tasks.DEFAULT_CHUNK_SIZE,
        vectorize_tasks.DEFAULT_CHUNK_OVERLAP,
    )
    assert vectorize_tasks._resolve_chunk_config({}) == (
        vectorize_tasks.DEFAULT_CHUNK_SIZE,
        vectorize_tasks.DEFAULT_CHUNK_OVERLAP,
    )


def test_resolve_chunk_config_clamps_negative_overlap_to_zero():
    size, overlap = vectorize_tasks._resolve_chunk_config({"chunk_size": 500, "overlap": -5})
    assert size == 500
    assert overlap == 0


def test_chunk_text_for_embedding_returns_no_chunks_for_blank_text():
    assert vectorize_tasks._chunk_text_for_embedding("", 100, 10) == []
    assert vectorize_tasks._chunk_text_for_embedding("   \n\t ", 100, 10) == []
    assert vectorize_tasks._chunk_text_for_embedding(None, 100, 10) == []


def test_chunk_text_for_embedding_keeps_exact_length_text_as_single_chunk():
    text = "a" * 100
    assert vectorize_tasks._chunk_text_for_embedding(text, 100, 10) == [text]


def make_status_repo(nodes=()):
    upsert_calls: list[dict] = []
    lookup_calls: list[uuid.UUID] = []

    class FakeStatusRepo:
        def __init__(self, session):
            self.session = session

        async def get_nodes_by_row_id(self, row_id):
            lookup_calls.append(row_id)
            return list(nodes)

        async def upsert_node(self, **kwargs):
            upsert_calls.append(kwargs)

    return FakeStatusRepo, upsert_calls, lookup_calls


class FakeRedisClient:
    def __init__(self):
        self.publish = AsyncMock()
        self.aclose = AsyncMock()


async def test_publish_template_vector_status_skips_non_template_collections():
    collection = make_collection(collection_type="table")
    await vectorize_tasks._publish_template_vector_status(
        session=object(), collection=collection, row_id=ROW_ID
    )


async def test_publish_template_vector_status_skips_without_redis_url(monkeypatch):
    collection = make_collection(collection_type="template")
    from_url = Mock()
    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL=""))
    monkeypatch.setattr("redis.asyncio.from_url", from_url)
    await vectorize_tasks._publish_template_vector_status(
        session=object(), collection=collection, row_id=ROW_ID
    )
    from_url.assert_not_called()


async def test_publish_template_vector_status_skips_missing_rows(monkeypatch):
    collection = make_collection(collection_type="template")
    from_url = Mock()

    class FakeRowService:
        def __init__(self, _session):
            pass

        async def get_row_by_id(self, _collection, _row_id):
            return None

    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL="redis://fake"))
    monkeypatch.setattr("app.services.collection.row_service.CollectionRowService", FakeRowService)
    monkeypatch.setattr("redis.asyncio.from_url", from_url)
    session = FakeSession()
    await vectorize_tasks._publish_template_vector_status(session=session, collection=collection, row_id=ROW_ID)
    from_url.assert_not_called()
    assert session.executed == []


async def test_publish_template_vector_status_publishes_row_and_collection_snapshots(monkeypatch):
    collection = make_collection(collection_type="template")
    session = FakeSession()
    session.row_meta = {"id": ROW_ID, "_vector_status": "done", "_vector_error": None, "_vector_chunk_count": 2}
    node = SimpleNamespace(
        node_key="vectorization",
        status="completed",
        error_short=None,
        metrics_json=None,
        started_at=None,
        finished_at=None,
    )
    repo, _, lookup_calls = make_status_repo(nodes=[node])
    client = FakeRedisClient()
    row = {
        "id": ROW_ID,
        "title": "Template A",
        "status": "uploaded",
        "description": "desc",
        "template_schema": None,
    }

    class FakeRowService:
        def __init__(self, _session):
            pass

        async def get_row_by_id(self, _collection, row_id):
            assert row_id == uuid.UUID(ROW_ID)
            return dict(row)

    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL="redis://fake"))
    monkeypatch.setattr("app.services.collection.row_service.CollectionRowService", FakeRowService)
    monkeypatch.setattr(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository", repo
    )
    monkeypatch.setattr("redis.asyncio.from_url", Mock(return_value=client))

    await vectorize_tasks._publish_template_vector_status(session=session, collection=collection, row_id=ROW_ID)

    assert lookup_calls == [uuid.UUID(ROW_ID)]
    assert client.publish.await_count == 2
    row_call, collection_call = client.publish.await_args_list
    row_event = json.loads(row_call.args[1])
    assert row_call.args[0] == f"template:row:{ROW_ID}"
    assert row_event["event_type"] == "snapshot"
    assert row_event["row_id"] == ROW_ID
    assert row_event["vectorization_status"] == "completed"
    collection_event = json.loads(collection_call.args[1])
    assert collection_call.args[0] == f"template:collection:{COLLECTION_ID}"
    assert collection_event["event_type"] == "snapshot"
    assert collection_event["collection_id"] == COLLECTION_ID
    assert collection_event["row_id"] == ROW_ID
    assert collection_event["item"]["id"] == ROW_ID
    client.aclose.assert_awaited_once()


async def test_upsert_template_retrieval_node_converts_ids_and_passes_kwargs(monkeypatch):
    repo, upsert_calls, _ = make_status_repo()
    monkeypatch.setattr(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository", repo
    )
    started = datetime(2026, 1, 2, tzinfo=timezone.utc)
    finished = datetime(2026, 1, 2, 3, tzinfo=timezone.utc)
    await vectorize_tasks._upsert_template_retrieval_node(
        session=FakeSession(),
        collection_id=COLLECTION_ID,
        row_id=ROW_ID,
        node_key="vectorization",
        status="failed",
        error_short="qdrant down",
        metrics_json={"chunks": 1},
        started_at=started,
        finished_at=finished,
    )
    assert upsert_calls == [
        {
            "collection_id": uuid.UUID(COLLECTION_ID),
            "row_id": uuid.UUID(ROW_ID),
            "node_key": "vectorization",
            "status": "failed",
            "error_short": "qdrant down",
            "metrics_json": {"chunks": 1},
            "started_at": started,
            "finished_at": finished,
        }
    ]


async def test_upsert_template_retrieval_node_defaults_optional_kwargs(monkeypatch):
    repo, upsert_calls, _ = make_status_repo()
    monkeypatch.setattr(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository", repo
    )
    await vectorize_tasks._upsert_template_retrieval_node(
        session=FakeSession(),
        collection_id=COLLECTION_ID,
        row_id=ROW_ID,
        node_key="indexing",
        status="pending",
    )
    assert upsert_calls == [
        {
            "collection_id": uuid.UUID(COLLECTION_ID),
            "row_id": uuid.UUID(ROW_ID),
            "node_key": "indexing",
            "status": "pending",
            "error_short": None,
            "metrics_json": None,
            "started_at": None,
            "finished_at": None,
        }
    ]


def make_orchestrator():
    enqueued: list[dict] = []
    reconciles: list[dict] = []

    class FakeOrchestrator:
        def __init__(self, session):
            self.session = session

        async def reconcile_pending_collections(self, *, limit, countdown):
            reconciles.append({"limit": limit, "countdown": countdown})
            return {"reconciled": limit, "enqueued": ["c1"]}

        @staticmethod
        def enqueue(**kwargs):
            enqueued.append(kwargs)

    return FakeOrchestrator, enqueued, reconciles


def run_vectorize(collection_id=COLLECTION_ID, tenant_id=TENANT_ID, row_ids=None):
    if row_ids is None:
        return vectorize_tasks.vectorize_collection_rows.run(collection_id, tenant_id)
    return vectorize_tasks.vectorize_collection_rows.run(collection_id, tenant_id, row_ids)


def test_vectorize_skips_when_advisory_lock_is_held(monkeypatch):
    session = FakeSession()
    session.lock_acquired = False
    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    result = run_vectorize()
    assert result == {"status": "skipped", "message": "already_running"}
    assert session.executed_with("pg_try_advisory_lock") == [
        {"lock_key": vectorize_tasks._collection_lock_key(COLLECTION_ID)}
    ]
    # The early return happens before the try/finally block, so no unlock is issued.
    assert session.executed_with("pg_advisory_unlock") == []


def test_vectorize_tolerates_unlock_failure(monkeypatch):
    session = FakeSession()
    session.unlock_error = RuntimeError("db gone")
    collection = make_collection()

    class FakeCollectionService:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _collection_id):
            return None

    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr("app.services.collection_service.CollectionService", FakeCollectionService)
    result = run_vectorize()
    assert result == {"status": "error", "message": "collection_not_found"}
    assert session.executed_with("pg_advisory_unlock")


def test_vectorize_returns_collection_not_found_when_missing(monkeypatch):
    session = FakeSession()

    class FakeCollectionService:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _collection_id):
            return None

    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr("app.services.collection_service.CollectionService", FakeCollectionService)
    assert run_vectorize() == {"status": "error", "message": "collection_not_found"}
    session.commit.assert_not_awaited()


def test_vectorize_returns_collection_not_found_for_other_tenant(monkeypatch):
    session = FakeSession()
    collection = make_collection(tenant_id="99999999-9999-9999-9999-999999999999")
    collection_service, _ = make_collection_service(collection)
    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr("app.services.collection_service.CollectionService", collection_service)
    assert run_vectorize() == {"status": "error", "message": "collection_not_found"}
    session.commit.assert_not_awaited()


def test_vectorize_skips_collection_without_qdrant_name(monkeypatch):
    session = FakeSession()
    collection = make_collection(qdrant_collection_name=None)
    collection_service, _ = make_collection_service(collection)
    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr("app.services.collection_service.CollectionService", collection_service)
    assert run_vectorize() == {"status": "skipped", "message": "no_qdrant_collection"}
    session.commit.assert_not_awaited()


def test_vectorize_skips_collection_without_vector_fields(monkeypatch):
    session = FakeSession()
    collection = make_collection(fields=[])
    collection_service, _ = make_collection_service(collection)
    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr("app.services.collection_service.CollectionService", collection_service)
    assert run_vectorize() == {"status": "skipped", "message": "no_vector_fields"}
    session.commit.assert_not_awaited()


def test_vectorize_fails_when_no_embedding_models_resolved(monkeypatch):
    session = FakeSession()
    collection = make_collection()
    wire_vectorize(monkeypatch, session, collection, aliases=())
    assert run_vectorize() == {"status": "error", "message": "no_embedding_models"}
    session.commit.assert_not_awaited()


def test_vectorize_reports_no_pending_rows(monkeypatch):
    session = FakeSession()
    collection = make_collection(vector_config=matching_vector_config())
    store, synced = wire_vectorize(monkeypatch, session, collection)
    result = run_vectorize()
    assert result == {"status": "ok", "vectorized": 0, "message": "no_pending_rows"}
    store.delete_by_filter.assert_not_awaited()
    store.upsert.assert_not_awaited()
    store.ensure_collection.assert_awaited_once_with(TABLE_NAME, 8)
    assert synced == []
    session.commit.assert_not_awaited()


def test_vectorize_happy_path_single_target(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello world"}]
    collection = make_collection(vector_config=matching_vector_config())
    store, synced = wire_vectorize(monkeypatch, session, collection)
    orchestrator_cls, enqueued, _ = make_orchestrator()
    monkeypatch.setattr(
        "app.services.collection_vectorization_orchestrator.CollectionVectorizationOrchestrator",
        orchestrator_cls,
    )

    result = run_vectorize()

    assert result == {"status": "ok", "vectorized": 1, "failed": 0, "total_chunks": 1, "remaining": 0}
    store.ensure_collection.assert_awaited_once_with(TABLE_NAME, 8)
    store.delete_by_filter.assert_awaited_once_with(TABLE_NAME, {"row_id": ROW_ID})
    upsert_call = store.upsert.await_args
    assert upsert_call.args[0] == TABLE_NAME
    assert upsert_call.args[1] == [[0.5] * 8]
    assert upsert_call.args[2] == [
        {
            "row_id": ROW_ID,
            "field_name": "body",
            "chunk_idx": 0,
            "text": "hello world",
            "embed_model_alias": "emb-default",
            "embedding_fingerprint": "fp-emb-default",
            "version": "v1",
            "tenant_id": TENANT_ID,
            "collection_id": COLLECTION_ID,
        }
    ]
    assert upsert_call.args[3] == [
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"{COLLECTION_ID}:{ROW_ID}:body:0"))
    ]
    assert session.executed_with("UPDATE", "_vector_status = 'done'") == [{"cnt": 1, "rid": ROW_ID}]
    assert session.executed_with("UPDATE collections") == [
        {"vectorized_rows": 0, "total_chunks": 0, "failed_rows": 0, "cid": COLLECTION_ID}
    ]
    session.commit.assert_awaited_once()
    assert enqueued == []
    assert synced == [(collection, False)]


def expected_point_payload(alias, text):
    return {
        "row_id": ROW_ID,
        "field_name": "body",
        "chunk_idx": 0,
        "text": text,
        "embed_model_alias": alias,
        "embedding_fingerprint": f"fp-{alias}",
        "version": "v1",
        "tenant_id": TENANT_ID,
        "collection_id": COLLECTION_ID,
    }


def test_vectorize_multi_target_upserts_each_scoped_collection(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello"}]
    aliases = ("emb-default", "emb-tenant")
    collection = make_collection(vector_config=matching_vector_config(*aliases))
    store, _ = wire_vectorize(monkeypatch, session, collection, aliases=aliases)

    result = run_vectorize()

    assert result == {"status": "ok", "vectorized": 1, "failed": 0, "total_chunks": 2, "remaining": 0}
    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{COLLECTION_ID}:{ROW_ID}:body:0"))
    assert store.delete_by_filter.await_args_list == [
        call(TABLE_NAME, {"row_id": ROW_ID}),
        call(f"{TABLE_NAME}__emb-tenant", {"row_id": ROW_ID}),
    ]
    assert store.upsert.await_args_list == [
        call(TABLE_NAME, [[0.5] * 8], [expected_point_payload("emb-default", "hello")], [point_id]),
        call(
            f"{TABLE_NAME}__emb-tenant",
            [[0.5] * 8],
            [expected_point_payload("emb-tenant", "hello")],
            [point_id],
        ),
    ]
    assert store.ensure_collection.await_args_list == [
        call(TABLE_NAME, 8),
        call(f"{TABLE_NAME}__emb-tenant", 8),
    ]


def test_vectorize_revectorizes_when_encoder_fingerprints_stale(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello"}]
    collection = make_collection(
        vector_config={
            "embed_model_aliases": ["emb-stale"],
            "index_fingerprints": {"emb-stale": "fp-stale"},
        }
    )
    store, _ = wire_vectorize(monkeypatch, session, collection)

    result = run_vectorize(row_ids=[ROW_ID, ROW_ID_2])

    assert result["status"] == "ok"
    assert len(session.executed_with("SET _vector_status='pending', _vector_chunk_count=0, _vector_error=NULL")) == 1
    session.flush.assert_awaited_once()
    assert collection.vector_config == {
        "embed_model_aliases": ["emb-default"],
        "index_fingerprints": {"emb-default": "fp-emb-default"},
    }
    # Explicit row_ids are ignored after revectorization: the batch SELECT has no IN list.
    assert not any("IN (" in sql for sql in session.executed)
    assert session.executed_with("LIMIT :lim") == [{"lim": 50}]
    store.upsert.assert_awaited_once()


def test_vectorize_selects_explicit_row_ids(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello"}]
    collection = make_collection(vector_config=matching_vector_config("emb-default"))
    store, _ = wire_vectorize(monkeypatch, session, collection)

    result = run_vectorize(row_ids=[ROW_ID, ROW_ID_2])

    assert result["vectorized"] == 1
    assert session.executed_with("LIMIT :lim") == [{"rid_0": ROW_ID, "rid_1": ROW_ID_2, "lim": 50}]
    store.upsert.assert_awaited_once()


def test_vectorize_marks_failed_row_and_still_commits(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello"}]
    collection = make_collection(vector_config=matching_vector_config())
    store, _ = wire_vectorize(monkeypatch, session, collection)
    store.delete_by_filter.side_effect = RuntimeError("qdrant down")

    result = run_vectorize()

    assert result == {"status": "ok", "vectorized": 0, "failed": 1, "total_chunks": 0, "remaining": 0}
    store.upsert.assert_not_awaited()
    assert session.executed_with("UPDATE", "_vector_status = 'error'") == [
        {"err": "qdrant down", "rid": ROW_ID}
    ]
    session.commit.assert_awaited_once()


def test_vectorize_enqueues_continuation_when_rows_remain(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello"}]
    session.remaining = 3
    collection = make_collection(vector_config=matching_vector_config())
    wire_vectorize(monkeypatch, session, collection)
    orchestrator_cls, enqueued, _ = make_orchestrator()
    monkeypatch.setattr(
        "app.services.collection_vectorization_orchestrator.CollectionVectorizationOrchestrator",
        orchestrator_cls,
    )

    result = run_vectorize()

    assert result["remaining"] == 3
    assert enqueued == [{"collection_id": COLLECTION_ID, "tenant_id": TENANT_ID, "countdown": 2}]


def test_vectorize_template_row_updates_nodes_and_marks_ready(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello"}]
    collection = make_collection(collection_type="template", vector_config=matching_vector_config())
    wire_vectorize(monkeypatch, session, collection)
    repo, upsert_calls, _ = make_status_repo()
    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL=""))
    monkeypatch.setattr(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository", repo
    )

    result = run_vectorize()

    assert result == {"status": "ok", "vectorized": 1, "failed": 0, "total_chunks": 1, "remaining": 0}
    assert [(call["node_key"], call["status"]) for call in upsert_calls] == [
        ("vectorization", "processing"),
        ("indexing", "pending"),
        ("indexing", "processing"),
        ("vectorization", "completed"),
        ("indexing", "completed"),
    ]
    assert all(call["collection_id"] == uuid.UUID(COLLECTION_ID) for call in upsert_calls)
    assert all(call["row_id"] == uuid.UUID(ROW_ID) for call in upsert_calls)
    assert upsert_calls[2]["metrics_json"] == {"model_alias": "emb-default", "chunks_prepared": 1}
    assert upsert_calls[4]["metrics_json"] == {
        "model_alias": "emb-default",
        "chunk_count": 1,
        "indexed_count": 1,
    }
    assert session.executed_with("status = 'ready'") == [{"rid": ROW_ID}]
    session.commit.assert_awaited_once()


def test_vectorize_template_row_records_failed_nodes_on_error(monkeypatch):
    session = FakeSession()
    session.pending_rows = [{"id": ROW_ID, "body": "hello"}]
    collection = make_collection(collection_type="template", vector_config=matching_vector_config())
    store, _ = wire_vectorize(monkeypatch, session, collection)
    store.delete_by_filter.side_effect = RuntimeError("qdrant down")
    repo, upsert_calls, _ = make_status_repo()
    monkeypatch.setattr("app.core.config.get_settings", lambda: SimpleNamespace(REDIS_URL=""))
    monkeypatch.setattr(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository", repo
    )

    result = run_vectorize()

    assert result == {"status": "ok", "vectorized": 0, "failed": 1, "total_chunks": 0, "remaining": 0}
    assert [(call["node_key"], call["status"]) for call in upsert_calls] == [
        ("vectorization", "processing"),
        ("indexing", "pending"),
        ("vectorization", "failed"),
        ("indexing", "failed"),
    ]
    for call in upsert_calls[2:]:
        assert call["error_short"] == "qdrant down"
        assert call["metrics_json"] == {"error_type": "RuntimeError"}
    assert session.executed_with("UPDATE", "_vector_status = 'error'") == [
        {"err": "qdrant down", "rid": ROW_ID}
    ]
    assert session.executed_with("status = 'ready'") == []


def test_reconcile_collection_vectorization_passes_limit_to_orchestrator(monkeypatch):
    session = FakeSession()
    orchestrator, _, reconciles = make_orchestrator()
    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr(
        "app.services.collection_vectorization_orchestrator.CollectionVectorizationOrchestrator",
        orchestrator,
    )

    result = vectorize_tasks.reconcile_collection_vectorization.run(limit=5)

    assert result == {"reconciled": 5, "enqueued": ["c1"]}
    assert reconciles == [{"limit": 5, "countdown": 1}]
    session.commit.assert_awaited_once()


def test_reconcile_collection_vectorization_propagates_orchestrator_errors(monkeypatch):
    session = FakeSession()
    orchestrator, _, _ = make_orchestrator()

    class FailingOrchestrator(orchestrator):
        async def reconcile_pending_collections(self, *, limit, countdown):
            raise RuntimeError("db down")

    monkeypatch.setattr("app.workers.session_factory.get_worker_session", make_session_scope(session))
    monkeypatch.setattr(
        "app.services.collection_vectorization_orchestrator.CollectionVectorizationOrchestrator",
        FailingOrchestrator,
    )

    with pytest.raises(RuntimeError, match="db down"):
        vectorize_tasks.reconcile_collection_vectorization.run(limit=5)
    session.commit.assert_not_awaited()
