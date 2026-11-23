"""Unit tests for app.workers.tasks_rag_ingest.index."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict, deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.storage.paths import get_idempotency_key
from app.workers.tasks_rag_ingest import index as index_mod
from app.workers.tasks_rag_ingest.index import _build_stable_point_id, _prefilter_payload_key
from app.workers.tasks_rag_ingest.stage_results import IndexResult

TENANT = uuid.uuid4()
SOURCE = uuid.uuid4()

CHUNKS_KEY = f"{TENANT}/{SOURCE}/chunks.jsonl"
EMB_KEY = f"{TENANT}/{SOURCE}/embeddings/m1/emb.jsonl"
K_MEMBERSHIP = "DocumentCollectionMembership.collection_id"


# ── fakes ────────────────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, pop):
        self._pop = pop

    def scalar_one_or_none(self):
        return self._pop()

    def scalars(self):
        return self

    def all(self):
        return self._pop()

    def first(self):
        return self._pop()


class FakeSession:
    def __init__(self):
        self.queue: dict[str, deque] = defaultdict(deque)
        self.queries: list[str] = []
        self.commit_calls = 0

    def q(self, key: str, *items) -> None:
        for item in items:
            self.queue[key].append(item)

    def _pop(self, key: str):
        dq = self.queue.get(key)
        return dq.popleft() if dq else None

    @staticmethod
    def _key(stmt) -> str:
        expr = stmt.column_descriptions[0]["expr"]
        if isinstance(expr, type):
            return expr.__name__
        return f"{expr.class_.__name__}.{expr.key}"

    async def execute(self, stmt):
        key = self._key(stmt)
        self.queries.append(key)
        return FakeResult(lambda: self._pop(key))

    async def commit(self):
        self.commit_calls += 1


class _NullLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRedis:
    def __init__(self):
        self.store: dict = {}
        self.get_calls: list = []
        self.locks: list = []

    async def get(self, key):
        self.get_calls.append(key)
        return self.store.get(key)

    def lock(self, key, timeout=None, blocking_timeout=None):
        self.locks.append((key, timeout, blocking_timeout))
        return _NullLock()


def make_ctx(
    session: FakeSession | None = None,
    redis: FakeRedis | None = None,
    generation: int | None = 3,
    celery_task_id: str | None = "celery-1",
):
    return SimpleNamespace(
        session=session or FakeSession(),
        redis=redis or FakeRedis(),
        tenant_id=TENANT,
        tenant_id_str=str(TENANT),
        source_id=SOURCE,
        settings=SimpleNamespace(S3_BUCKET_RAG="rag-bucket"),
        generation=generation,
        celery_task_id=celery_task_id,
        elapsed_sec=1.25,
        set_processing=AsyncMock(),
        set_completed=AsyncMock(),
        check_idempotency=AsyncMock(return_value=None),
        save_idempotency=AsyncMock(),
        is_current_generation=AsyncMock(return_value=True),
    )


def chunk_row(cid, page=1, lang="en", text="hello"):
    return SimpleNamespace(chunk_id=cid, page=page, lang=lang,
                           meta={"text": text} if text is not None else None)


def source_meta(embedding_artifacts=None, prefilter=None, chunks_key=CHUNKS_KEY):
    meta: dict = {"artifacts": {"chunks": {"key": chunks_key}}}
    if embedding_artifacts is not None:
        meta["embedding_artifacts"] = embedding_artifacts
    if prefilter is not None:
        meta["collection"] = {"prefilter": prefilter}
    return meta


def artifact_line(cid, vector=None, chunks_key=CHUNKS_KEY, fingerprint="fp-1", **extra):
    record = {
        "chunk_id": cid,
        "vector": vector or [0.1, 0.2, 0.3],
        "chunks_key": chunks_key,
        "embedding_fingerprint": fingerprint,
    }
    record.update(extra)
    return json.dumps(record)


def install_repos(monkeypatch, chunks, source):
    made: dict = {}

    def chunk_ctor(session, tenant_id):
        made["chunk"] = (session, tenant_id)
        return SimpleNamespace(get_by_source_id=AsyncMock(return_value=chunks))

    def source_ctor(session, tenant_id):
        return SimpleNamespace(get_by_id=AsyncMock(return_value=source))

    monkeypatch.setattr(index_mod, "AsyncChunkRepository", chunk_ctor)
    monkeypatch.setattr(index_mod, "AsyncSourceRepository", source_ctor)
    return made


def install_qdrant(monkeypatch, collection_exists=True):
    made: dict = {}
    # Pre-created so tests can override mocks BEFORE the store is constructed
    # inside index_model.run(); __init__ copies whatever is present at that time.
    inst = SimpleNamespace(
        upsert=AsyncMock(),
        ensure_collection=AsyncMock(),
        delete_points=AsyncMock(),
        delete_document_points_before_generation=AsyncMock(),
        collection_exists=AsyncMock(return_value=collection_exists),
    )
    made["instance"] = inst
    _attrs = ("upsert", "ensure_collection", "delete_points",
              "delete_document_points_before_generation", "collection_exists")

    class FakeQdrant:
        def __init__(self):
            for name in _attrs:
                setattr(self, name, getattr(inst, name))

    monkeypatch.setattr("app.adapters.impl.qdrant.QdrantVectorStore", FakeQdrant)
    return made


def install_vector_index(monkeypatch, target, cache_current=False):
    calls: dict = {}

    class FakeVIS:
        def __init__(self, session):
            calls["session"] = session

        async def resolve(self, base_name, alias):
            calls["resolve"] = (base_name, alias)
            return target

    cache_mock = AsyncMock(return_value=cache_current)
    FakeVIS.cache_is_current = cache_mock
    monkeypatch.setattr("app.services.vector_index_service.VectorIndexService", FakeVIS)
    return calls, cache_mock


def install_s3(monkeypatch, content: str, listed=None):
    calls: dict = {}

    async def fake_download(*, bucket, key, file_path):
        calls["download"] = (bucket, key, file_path)
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return True

    s3 = SimpleNamespace(
        download_file=fake_download,
        list_objects=AsyncMock(
            side_effect=lambda **kw: (
                calls.setdefault("list_objects", []).append(kw), listed or [])[1]),
    )
    monkeypatch.setattr(index_mod, "s3_manager", s3)
    return calls


def make_target():
    return SimpleNamespace(collection_name="coll-resolved", fingerprint="fp-1",
                           version="v9", dimensions=3)


def capture_run_stage(monkeypatch, ctx=None):
    captured: dict = {}

    def fake_run_stage(*, stage_name, source_id, tenant_id, celery_task,
                       execute_fn, run_id=None, generation=None):
        captured.update(
            stage_name=stage_name, source_id=source_id, tenant_id=tenant_id,
            celery_task=celery_task, run_id=run_id, generation=generation,
            execute_fn=execute_fn,
        )
        if ctx is not None:
            return asyncio.run(execute_fn(ctx))
        return "stage-result"

    monkeypatch.setattr(index_mod, "run_stage", fake_run_stage)
    return captured


def embed_payload(embeddings_key=EMB_KEY, model_alias="m1"):
    payload = {
        "source_id": str(SOURCE),
        "model_alias": model_alias,
        "count": 2,
    }
    if embeddings_key is not None:
        payload["embeddings_key"] = embeddings_key
    return payload


# ── pure helpers ─────────────────────────────────────────────────────────


class TestBuildStablePointId:
    def test_deterministic_for_same_inputs(self):
        a = _build_stable_point_id("t", "s", "m", "c1", generation=2, attempt_id="a1")
        b = _build_stable_point_id("t", "s", "m", "c1", generation=2, attempt_id="a1")
        assert a == b
        assert a == str(uuid.uuid5(uuid.UUID("4b32c67e-86c7-4efb-8980-1e0570f31d16"),
                                   "t:s:m:2:a1:c1"))

    def test_changes_with_attempt_and_generation(self):
        base = _build_stable_point_id("t", "s", "m", "c1", generation=2, attempt_id="a1")
        assert _build_stable_point_id("t", "s", "m", "c1", generation=3, attempt_id="a1") != base
        assert _build_stable_point_id("t", "s", "m", "c1", generation=2, attempt_id="a2") != base

    def test_none_generation_equals_zero(self):
        none = _build_stable_point_id("t", "s", "m", "c1", generation=None)
        zero = _build_stable_point_id("t", "s", "m", "c1", generation=0)
        assert none == zero


class TestPrefilterPayloadKey:
    def test_lowercases_and_sanitizes(self):
        assert _prefilter_payload_key("Department ID") == "pf_department_id"

    def test_non_string_field_name(self):
        assert _prefilter_payload_key(123) == "pf_123"


# ── task entry ───────────────────────────────────────────────────────────


class TestTaskEntry:
    def test_dict_with_source_id_parses_embed_result(self, monkeypatch):
        captured = capture_run_stage(monkeypatch)

        result = index_mod.index_model.run(
            embed_payload(), str(TENANT), run_id="run-1", generation=3)

        assert result == "stage-result"
        assert captured["stage_name"] == "index.m1"
        assert captured["source_id"] == str(SOURCE)
        assert captured["tenant_id"] == str(TENANT)
        assert captured["run_id"] == "run-1"
        assert captured["generation"] == 3
        assert captured["celery_task"] == index_mod.index_model
        assert callable(captured["execute_fn"])

    def test_dict_without_source_id_uses_get(self, monkeypatch):
        captured = capture_run_stage(monkeypatch)

        index_mod.index_model.run({"model_alias": "m2"}, str(TENANT))

        assert captured["source_id"] == ""
        assert captured["stage_name"] == "index.m2"


# ── _execute: embeddings key resolution ──────────────────────────────────


class TestEmbeddingsKeyResolution:
    def test_payload_key_used_directly(self, monkeypatch):
        ctx = make_ctx()
        target = make_target()
        install_vector_index(monkeypatch, target)
        install_qdrant(monkeypatch)
        s3 = install_s3(
            monkeypatch,
            artifact_line("c1") + "\n" + artifact_line("c2") + "\n")
        install_repos(
            monkeypatch,
            [chunk_row("c1"), chunk_row("c2")],
            SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        captured = capture_run_stage(monkeypatch, ctx)

        result = index_mod.index_model.run(embed_payload(embeddings_key=EMB_KEY), str(TENANT))

        assert isinstance(result, IndexResult)
        # embed idem key and S3 listing were never consulted
        assert ctx.redis.get_calls == []
        assert "list_objects" not in s3
        assert s3["download"][1] == EMB_KEY

    def test_redis_embed_idem_json_hit(self, monkeypatch):
        ctx = make_ctx()
        redis = ctx.redis
        redis.store[get_idempotency_key(TENANT, SOURCE, "embed", "m1")] = json.dumps(
            {"embeddings_key": "from-redis.jsonl"})
        install_vector_index(monkeypatch, make_target())
        install_qdrant(monkeypatch)
        s3 = install_s3(
            monkeypatch, artifact_line("c1") + "\n" + artifact_line("c2") + "\n")
        install_repos(
            monkeypatch,
            [chunk_row("c1"), chunk_row("c2")],
            SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(embeddings_key=None), str(TENANT))

        assert get_idempotency_key(TENANT, SOURCE, "embed", "m1") in redis.get_calls
        assert s3["download"][1] == "from-redis.jsonl"

    def test_redis_embed_idem_invalid_json_falls_through(self, monkeypatch):
        ctx = make_ctx()
        ctx.redis.store[get_idempotency_key(TENANT, SOURCE, "embed", "m1")] = "not-json{"
        install_vector_index(monkeypatch, make_target())
        install_qdrant(monkeypatch)
        s3 = install_s3(
            monkeypatch, artifact_line("c1") + "\n" + artifact_line("c2") + "\n")
        install_repos(
            monkeypatch,
            [chunk_row("c1"), chunk_row("c2")],
            SimpleNamespace(meta=source_meta(
                embedding_artifacts={"m1": {"key": "from-meta.jsonl"}})))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(embeddings_key=None), str(TENANT))

        assert s3["download"][1] == "from-meta.jsonl"

    def test_source_meta_artifact_dict_and_string(self, monkeypatch):
        for artifact, expected in (
            ({"key": "dict-key.jsonl"}, "dict-key.jsonl"),
            ("plain-key.jsonl", "plain-key.jsonl"),
        ):
            ctx = make_ctx()
            install_vector_index(monkeypatch, make_target())
            install_qdrant(monkeypatch)
            s3 = install_s3(
                monkeypatch, artifact_line("c1") + "\n" + artifact_line("c2") + "\n")
            install_repos(
                monkeypatch,
                [chunk_row("c1"), chunk_row("c2")],
                SimpleNamespace(meta=source_meta(embedding_artifacts={"m1": artifact})))
            ctx.session.q(K_MEMBERSHIP, None)
            capture_run_stage(monkeypatch, ctx)

            index_mod.index_model.run(embed_payload(embeddings_key=None), str(TENANT))

            assert s3["download"][1] == expected

    def test_s3_listing_picks_latest_jsonl(self, monkeypatch):
        ctx = make_ctx()
        install_vector_index(monkeypatch, make_target())
        install_qdrant(monkeypatch)
        s3 = install_s3(
            monkeypatch, artifact_line("c1") + "\n" + artifact_line("c2") + "\n",
            listed=[
                {"Key": "old.jsonl", "LastModified": "2026-01-01T00:00:00Z"},
                "not-a-dict",
                {"Key": "new.jsonl", "LastModified": "2026-02-01T00:00:00Z"},
                {"Key": "ignored.txt", "LastModified": "2026-03-01T00:00:00Z"},
            ])
        install_repos(
            monkeypatch,
            [chunk_row("c1"), chunk_row("c2")],
            SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(embeddings_key=None), str(TENANT))

        listing = s3["list_objects"][0]
        assert listing["prefix"] == f"{TENANT}/{SOURCE}/embeddings/m1/"
        assert listing["bucket"] == "rag-bucket"
        assert listing["max_keys"] == 200
        assert s3["download"][1] == "new.jsonl"

    def test_no_key_anywhere_raises(self, monkeypatch):
        ctx = make_ctx()
        install_s3(monkeypatch, "", listed=[])
        install_repos(monkeypatch, [chunk_row("c1")], SimpleNamespace(meta=source_meta()))
        capture_run_stage(monkeypatch, ctx)

        with pytest.raises(ValueError, match="No embeddings_key provided"):
            index_mod.index_model.run(embed_payload(embeddings_key=None), str(TENANT))


# ── _execute: preconditions ──────────────────────────────────────────────


class TestValidationPreconditions:
    def test_no_canonical_chunks_raises(self, monkeypatch):
        ctx = make_ctx()
        install_repos(monkeypatch, [], SimpleNamespace(meta=source_meta()))
        capture_run_stage(monkeypatch, ctx)

        with pytest.raises(ValueError, match="No canonical chunks found"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_no_canonical_chunks_artifact_raises(self, monkeypatch):
        ctx = make_ctx()
        install_repos(
            monkeypatch, [chunk_row("c1")],
            SimpleNamespace(meta={"artifacts": {"chunks": {}}}))
        capture_run_stage(monkeypatch, ctx)

        with pytest.raises(ValueError, match="No canonical chunks artifact"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_missing_source_row_means_no_artifact(self, monkeypatch):
        ctx = make_ctx()
        install_repos(monkeypatch, [chunk_row("c1")], None)
        capture_run_stage(monkeypatch, ctx)

        with pytest.raises(ValueError, match="No canonical chunks artifact"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_non_dict_prefilter_ignored(self, monkeypatch):
        ctx = make_ctx()
        install_vector_index(monkeypatch, make_target())
        qdrant = install_qdrant(monkeypatch)
        install_s3(monkeypatch, artifact_line("c1") + "\n")
        install_repos(
            monkeypatch, [chunk_row("c1")],
            SimpleNamespace(meta={"artifacts": {"chunks": {"key": CHUNKS_KEY}},
                                  "collection": {"prefilter": "bad"}}))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(), str(TENANT))
        payload = qdrant["instance"].upsert.await_args.args[2][0]
        assert not any(k.startswith("pf_") for k in payload)


# ── _execute: happy path ─────────────────────────────────────────────────


class TestHappyPath:
    def test_full_upsert_flow(self, monkeypatch):
        ctx = make_ctx()
        session = ctx.session
        redis = ctx.redis
        target = make_target()
        vis_calls, _ = install_vector_index(monkeypatch, target)
        qdrant = install_qdrant(monkeypatch)
        install_s3(
            monkeypatch,
            artifact_line("c1") + "\n" + artifact_line("c2") + "\n")
        coll_id, row_id = uuid.uuid4(), uuid.uuid4()
        membership = SimpleNamespace(
            collection_id=coll_id, collection_row_id=row_id,
            qdrant_collection_name="coll-custom", vector_config={})
        install_repos(
            monkeypatch,
            [chunk_row("c1", page=2, lang="ru", text="привет"),
             chunk_row("c2", page=None, lang=None, text=None)],
            SimpleNamespace(meta=source_meta(prefilter={
                "Department": "Sales",
                "Priority": 2,
                "Tags": ["a", "b"],
                "Junk": [None, ["x"], 3],
                "Empty": [None, {}],
                "Object": {"k": 1},
            })))
        session.q(K_MEMBERSHIP, membership)
        capture_run_stage(monkeypatch, ctx)

        result = index_mod.index_model.run(embed_payload(), str(TENANT))

        assert isinstance(result, IndexResult)
        assert result.source_id == str(SOURCE)
        assert result.model_alias == "m1"
        assert result.indexed_count == 2
        assert result.collection == "coll-resolved"

        assert redis.locks == [(f"lock:index:{SOURCE}:m1", 3600, 5)]
        ctx.set_processing.assert_awaited_once()
        ctx.check_idempotency.assert_awaited_once_with(model_alias="m1")

        # membership routed to the collection's qdrant name
        assert vis_calls["resolve"] == ("coll-custom", "m1")
        assert vis_calls["session"] is session

        inst = qdrant["instance"]
        inst.ensure_collection.assert_awaited_once_with("coll-resolved", 3)

        args = inst.upsert.await_args.args
        collection_name, vectors, payloads, ids = args
        assert collection_name == "coll-resolved"
        assert vectors == [[0.1, 0.2, 0.3]] * 2

        expected_ids = [
            _build_stable_point_id(str(TENANT), str(SOURCE), "m1", cid,
                                   generation=3, attempt_id="celery-1")
            for cid in ("c1", "c2")
        ]
        assert ids == expected_ids

        p1, p2 = payloads
        assert p1["chunk_id"] == "c1"
        assert p1["page"] == 2
        assert p1["lang"] == "ru"
        assert p1["text"] == "привет"
        assert p1["pf_department"] == "Sales"
        assert p1["pf_priority"] == 2
        assert p1["pf_tags"] == ["a", "b"]
        assert p1["pf_junk"] == [3]
        assert "pf_empty" not in p1
        assert "pf_object" not in p1
        assert p1["collection_id"] == str(coll_id)
        assert p1["row_id"] == str(row_id)
        assert p1["embedding_fingerprint"] == "fp-1"
        assert p1["version"] == "v9"
        assert p1["index_version"] == index_mod._DOC_INDEX_VERSION
        assert p1["index_revision"] == index_mod._DOC_INDEX_VERSION
        assert p1["ingest_generation"] == 3
        assert p1["ingest_attempt_id"] == "celery-1"
        # page/lang defaults for None values
        assert p2["page"] == 0
        assert p2["lang"] == "en"
        assert p2["text"] == ""

        inst.delete_document_points_before_generation.assert_awaited_once_with(
            "coll-resolved", str(SOURCE), str(TENANT), 3, "celery-1")
        inst.delete_points.assert_not_awaited()

        ctx.set_completed.assert_awaited_once()
        metrics = ctx.set_completed.await_args.kwargs["metrics"]
        assert metrics["indexed_count"] == 2
        assert metrics["collection"] == "coll-resolved"
        assert metrics["model_version"] == "v9"
        assert metrics["embedding_fingerprint"] == "fp-1"
        assert metrics["duration_sec"] == 1.25

        ctx.save_idempotency.assert_awaited_once_with(
            {
                "status": "completed", "indexed_count": 2,
                "embedding_fingerprint": "fp-1", "collection": "coll-resolved",
                "embeddings_key": EMB_KEY,
            },
            model_alias="m1",
        )
        # commit after resolve + one per batch + final commit
        assert session.commit_calls == 3

    def test_default_collection_without_membership(self, monkeypatch):
        ctx = make_ctx()
        vis_calls, _ = install_vector_index(monkeypatch, make_target())
        qdrant = install_qdrant(monkeypatch)
        install_s3(monkeypatch, artifact_line("c1") + "\n")
        install_repos(
            monkeypatch, [chunk_row("c1")], SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(), str(TENANT))

        assert vis_calls["resolve"] == (f"{TENANT}__documents", "m1")
        payload = qdrant["instance"].upsert.await_args.args[2][0]
        assert "collection_id" not in payload
        assert "row_id" not in payload

    def test_membership_without_row_id_omits_row_id(self, monkeypatch):
        ctx = make_ctx()
        install_vector_index(monkeypatch, make_target())
        qdrant = install_qdrant(monkeypatch)
        install_s3(monkeypatch, artifact_line("c1") + "\n")
        install_repos(
            monkeypatch, [chunk_row("c1")], SimpleNamespace(meta=source_meta()))
        coll_id = uuid.uuid4()
        ctx.session.q(K_MEMBERSHIP, SimpleNamespace(
            collection_id=coll_id, collection_row_id=None,
            qdrant_collection_name=None, vector_config={}))
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(), str(TENANT))

        payload = qdrant["instance"].upsert.await_args.args[2][0]
        assert payload["collection_id"] == str(coll_id)
        assert "row_id" not in payload

    def test_attempt_id_falls_back_to_uuid(self, monkeypatch):
        ctx = make_ctx(celery_task_id=None)
        qdrant = install_qdrant(monkeypatch)
        install_vector_index(monkeypatch, make_target())
        install_s3(monkeypatch, artifact_line("c1") + "\n")
        install_repos(
            monkeypatch, [chunk_row("c1")], SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(), str(TENANT))

        inst = qdrant["instance"]
        attempt_id = inst.delete_document_points_before_generation.await_args.args[4]
        assert isinstance(attempt_id, str)
        assert len(attempt_id) == 36
        payload = inst.upsert.await_args.args[2][0]
        assert payload["ingest_attempt_id"] == attempt_id

    def test_batches_of_100(self, monkeypatch):
        ctx = make_ctx()
        qdrant = install_qdrant(monkeypatch)
        install_vector_index(monkeypatch, make_target())
        chunks = [chunk_row(f"c{i:03d}") for i in range(150)]
        content = "".join(artifact_line(c.chunk_id) + "\n" for c in chunks)
        install_s3(monkeypatch, content)
        install_repos(
            monkeypatch, chunks, SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        index_mod.index_model.run(embed_payload(), str(TENANT))

        inst = qdrant["instance"]
        assert inst.upsert.await_count == 2
        first = inst.upsert.await_args_list[0].args
        second = inst.upsert.await_args_list[1].args
        assert len(first[1]) == 100
        assert len(second[1]) == 50
        assert ctx.is_current_generation.await_count == 3  # 2 batches + final
        assert ctx.session.commit_calls == 4  # resolve + 2 batches + final

    def test_blank_lines_skipped_in_artifact(self, monkeypatch):
        ctx = make_ctx()
        qdrant = install_qdrant(monkeypatch)
        install_vector_index(monkeypatch, make_target())
        install_s3(
            monkeypatch, "\n" + artifact_line("c1") + "\n\n" + artifact_line("c2") + "\n")
        install_repos(
            monkeypatch, [chunk_row("c1"), chunk_row("c2")],
            SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        result = index_mod.index_model.run(embed_payload(), str(TENANT))

        assert result.indexed_count == 2


# ── _execute: already processed ──────────────────────────────────────────


class TestAlreadyProcessed:
    def test_cache_current_short_circuits(self, monkeypatch):
        ctx = make_ctx()
        ctx.check_idempotency = AsyncMock(return_value={"indexed_count": 7})
        target = make_target()
        cache_mock = install_vector_index(monkeypatch, target, cache_current=True)[1]
        qdrant = install_qdrant(monkeypatch)
        s3 = install_s3(monkeypatch, artifact_line("c1") + "\n")
        install_repos(
            monkeypatch, [chunk_row("c1")], SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        captured = capture_run_stage(monkeypatch, ctx)

        result = index_mod.index_model.run(embed_payload(), str(TENANT))

        assert isinstance(result, IndexResult)
        assert result.indexed_count == 7
        assert result.collection == "coll-resolved"

        cache_mock.assert_awaited_once()
        call_args = cache_mock.await_args
        assert call_args.args[0] is target
        assert call_args.args[1] == {"indexed_count": 7}
        assert call_args.args[2] == EMB_KEY
        assert call_args.args[4] == str(SOURCE)
        assert call_args.args[5] == str(TENANT)
        assert call_args.kwargs == {"expected_count": 1}

        qdrant["instance"].upsert.assert_not_awaited()
        assert "download" not in s3
        ctx.set_completed.assert_awaited_once()
        metrics = ctx.set_completed.await_args.kwargs["metrics"]
        assert metrics["status"] == "already_processed"
        assert metrics["cached"] is True
        assert metrics["indexed_count"] == 7
        ctx.save_idempotency.assert_not_awaited()


# ── _execute: artifact validation errors ─────────────────────────────────


class TestArtifactValidation:
    def _env(self, monkeypatch, content, chunks):
        ctx = make_ctx()
        install_vector_index(monkeypatch, make_target())
        qdrant = install_qdrant(monkeypatch)
        install_s3(monkeypatch, content)
        install_repos(
            monkeypatch, chunks, SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)
        return ctx, qdrant

    def test_non_object_record(self, monkeypatch):
        ctx, _ = self._env(monkeypatch, "[1, 2]\n", [chunk_row("c1")])
        with pytest.raises(ValueError, match="non-object record"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    @pytest.mark.parametrize("chunk_id", [None, 123, ""])
    def test_invalid_chunk_id(self, monkeypatch, chunk_id):
        line = json.dumps({"chunk_id": chunk_id, "vector": [0.1, 0.2, 0.3]})
        ctx, _ = self._env(monkeypatch, line + "\n", [chunk_row("c1")])
        with pytest.raises(ValueError, match="missing or invalid chunk_id"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_duplicate_chunk_id(self, monkeypatch):
        ctx, _ = self._env(
            monkeypatch, artifact_line("c1") + "\n" + artifact_line("c1") + "\n",
            [chunk_row("c1"), chunk_row("c2")])
        with pytest.raises(ValueError, match="duplicate chunk_id c1"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_unknown_chunk_id(self, monkeypatch):
        ctx, _ = self._env(
            monkeypatch, artifact_line("cX") + "\n",
            [chunk_row("c1")])
        with pytest.raises(ValueError, match="references unknown chunk_id"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_chunks_key_mismatch(self, monkeypatch):
        ctx, _ = self._env(
            monkeypatch, artifact_line("c1", chunks_key="other.jsonl") + "\n",
            [chunk_row("c1")])
        with pytest.raises(ValueError, match="another canonical input"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_fingerprint_mismatch(self, monkeypatch):
        ctx, _ = self._env(
            monkeypatch, artifact_line("c1", fingerprint="fp-other") + "\n",
            [chunk_row("c1")])
        with pytest.raises(ValueError, match="another or unknown vector space"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

    def test_incomplete_artifact(self, monkeypatch):
        ctx, qdrant = self._env(
            monkeypatch, artifact_line("c1") + "\n",
            [chunk_row("c1"), chunk_row("c2")])
        with pytest.raises(ValueError, match="Embedding artifact is incomplete"):
            index_mod.index_model.run(embed_payload(), str(TENANT))
        # validation happens before ensure/upsert — nothing written
        qdrant["instance"].ensure_collection.assert_not_awaited()
        qdrant["instance"].upsert.assert_not_awaited()


# ── _execute: failure handling ───────────────────────────────────────────


class TestFailureHandling:
    def _env(self, monkeypatch, *, chunks=None, collection_exists=True):
        ctx = make_ctx()
        install_vector_index(monkeypatch, make_target())
        qdrant = install_qdrant(monkeypatch, collection_exists=collection_exists)
        chunks = chunks or [chunk_row("c1")]
        install_s3(monkeypatch, artifact_line("c1") + "\n")
        install_repos(monkeypatch, chunks, SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)
        return ctx, qdrant

    def test_download_returns_false_raises_ioerror(self, monkeypatch):
        ctx = make_ctx()
        install_vector_index(monkeypatch, make_target())
        qdrant = install_qdrant(monkeypatch)

        async def failing_download(*, bucket, key, file_path):
            return False

        monkeypatch.setattr(
            index_mod, "s3_manager",
            SimpleNamespace(download_file=failing_download,
                            list_objects=AsyncMock(return_value=[])))
        install_repos(monkeypatch, [chunk_row("c1")], SimpleNamespace(meta=source_meta()))
        ctx.session.q(K_MEMBERSHIP, None)
        capture_run_stage(monkeypatch, ctx)

        with pytest.raises(IOError, match="Failed to download embeddings artifact"):
            index_mod.index_model.run(embed_payload(), str(TENANT))
        # upsert never started → no cleanup attempted
        qdrant["instance"].delete_points.assert_not_awaited()

    def test_upsert_retries_then_succeeds(self, monkeypatch):
        ctx, qdrant = self._env(monkeypatch)
        inst = qdrant["instance"]
        attempts: list[int] = []

        async def flaky_upsert(collection, vectors, payloads, ids):
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("qdrant down")
            return None

        inst.upsert = AsyncMock(side_effect=flaky_upsert)
        sleep_calls: list[float] = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)

        monkeypatch.setattr(index_mod.asyncio, "sleep", fake_sleep)

        result = index_mod.index_model.run(embed_payload(), str(TENANT))

        assert result.indexed_count == 1
        assert len(attempts) == 3
        assert sleep_calls == [0.3, 0.6]

    def test_upsert_retry_exhaustion_cleans_partial_points(self, monkeypatch):
        ctx, qdrant = self._env(monkeypatch)
        inst = qdrant["instance"]
        inst.upsert = AsyncMock(side_effect=RuntimeError("qdrant permanently down"))
        monkeypatch.setattr(
            index_mod.asyncio, "sleep", AsyncMock(return_value=None))

        with pytest.raises(RuntimeError, match="qdrant permanently down"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

        assert inst.upsert.await_count == 3
        inst.delete_points.assert_awaited_once()
        args = inst.delete_points.await_args.args
        assert args[0] == "coll-resolved"
        assert args[1] == [
            _build_stable_point_id(str(TENANT), str(SOURCE), "m1", "c1",
                                   generation=3, attempt_id="celery-1")]
        inst.delete_document_points_before_generation.assert_not_awaited()
        ctx.set_completed.assert_not_awaited()
        ctx.save_idempotency.assert_not_awaited()

    def test_cleanup_skipped_when_collection_missing(self, monkeypatch):
        ctx, qdrant = self._env(monkeypatch, collection_exists=False)
        inst = qdrant["instance"]
        inst.upsert = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

        inst.collection_exists.assert_awaited_once_with("coll-resolved")
        inst.delete_points.assert_not_awaited()

    def test_cleanup_failure_swallowed(self, monkeypatch):
        ctx, qdrant = self._env(monkeypatch)
        inst = qdrant["instance"]
        inst.upsert = AsyncMock(side_effect=RuntimeError("boom"))
        inst.delete_points = AsyncMock(side_effect=RuntimeError("cleanup failed"))

        with pytest.raises(RuntimeError, match="^boom$"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

        inst.delete_points.assert_awaited_once()

    def test_generation_change_before_upsert(self, monkeypatch):
        ctx, qdrant = self._env(monkeypatch)
        inst = qdrant["instance"]
        ctx.is_current_generation = AsyncMock(return_value=False)

        with pytest.raises(RuntimeError,
                           match="Ingest generation changed before vector upsert"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

        inst.upsert.assert_not_awaited()
        # upsert_started is still False → no point cleanup
        inst.delete_points.assert_not_awaited()
        assert ctx.session.commit_calls >= 2  # resolve + pre-batch commit

    def test_generation_change_after_upsert_deletes_written_points(self, monkeypatch):
        ctx, qdrant = self._env(monkeypatch)
        inst = qdrant["instance"]
        ctx.is_current_generation = AsyncMock(side_effect=[True, False])

        with pytest.raises(
                RuntimeError,
                match="Ingest generation changed while vectors were being indexed"):
            index_mod.index_model.run(embed_payload(), str(TENANT))

        inst.upsert.assert_awaited_once()
        # written points removed by the generation guard, then again by the
        # generic cleanup handler (the guard raises inside the try block)
        assert inst.delete_points.await_count == 2
        for call in inst.delete_points.await_args_list:
            assert call.args[0] == "coll-resolved"
            assert len(call.args[1]) == 1
        inst.delete_document_points_before_generation.assert_not_awaited()
