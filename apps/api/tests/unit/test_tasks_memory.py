"""Unit tests for app/workers/tasks_memory.py."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.models.memory import FactScope, FactSource
from app.workers import tasks_memory
from app.workers.tasks_memory import (
    MemoryFinalizePayload,
    _deserialize_turn_memory,
    _load_memory_prompts,
)


class FakeResult:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeSession:
    """Routes statements to per-lead-entity FIFO queues."""

    def __init__(self):
        self.delete_results: list[FakeResult] = []
        self.select_results: dict[type, list[FakeResult]] = {}
        self.get_map: dict[tuple, object] = {}
        self.executed: list[object] = []
        self.get_calls: list[tuple] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()

    def queue_select(self, entity, rows):
        self.select_results.setdefault(entity, []).append(FakeResult(rows=rows))

    async def execute(self, stmt):
        self.executed.append(stmt)
        if getattr(stmt, "__visit_name__", "") == "delete":
            return self.delete_results.pop(0)
        entity = stmt.column_descriptions[0]["entity"]
        queue = self.select_results.get(entity)
        if queue:
            return queue.pop(0)
        return FakeResult(rows=[])

    async def get(self, model, entity_id):
        self.get_calls.append((model, entity_id))
        return self.get_map.get((model, entity_id))


def make_session_scope(session):
    @asynccontextmanager
    async def scope():
        yield session

    return scope


def make_session_stack(*sessions):
    sessions = list(sessions)

    @asynccontextmanager
    async def scope():
        yield sessions.pop(0)

    return scope


def passthrough_transaction():
    @asynccontextmanager
    async def _wt(_session, _label):
        yield

    return _wt


def finalize_payload_dict(**over):
    base = {
        "chat_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "turn_number": 3,
        "user_message": "hello",
        "assistant_final": "hi",
        "summary": {
            "chat_id": "",
            "goals": ["g"],
            "done": ["d"],
            "entities": {"a": "b"},
            "open_questions": [],
            "raw_tail": "tail",
            "last_updated_turn": 2,
        },
        "retrieved_facts": [
            {
                "scope": "user",
                "subject": "s",
                "value": "v",
                "source": "USER_UTTERANCE",
                "tenant_id": None,
                "confidence": 0.9,
            }
        ],
        "agent_results": [{"agent": "a1", "summary": "s1", "success": True}],
        "fact_evidence": [
            {"source_id": "sid", "source_type": "user_message", "source_ref": "r", "text": "t", "label": None}
        ],
        "preflight_candidates": [{"subject": "p"}],
        "runtime_run_id": "run-1",
        "terminal_reason": None,
        "sandbox_overrides": None,
    }
    base.update(over)
    return base


DEFAULT_WRITE_STATUS = {
    "results": [
        {
            "component_name": "fact_extractor",
            "status": "completed",
            "decisions": [{"stage": "insert", "subject": "s"}, "not-a-dict"],
            "inserted_count": 2,
            "updated_count": 1,
            "skipped_count": 0,
            "duration_ms": 12,
            "facts": [{"subject": "s"}],
            "decision_counts": {"insert": 2},
        },
        {
            "component_name": "fact_compactor",
            "status": "failed",
            "decisions": [],
            "inserted_count": 0,
            "error_code": "E",
            "error_message": "m",
        },
    ],
    "failed_components": ["fact_compactor"],
    "degraded_components": [],
}


async def _default_writer_finalize(memory, llm_event_sink):
    from app.runtime.events import RuntimeEvent, RuntimeEventType

    await llm_event_sink(
        "fact_extractor",
        RuntimeEvent(
            RuntimeEventType.LLM_REQUEST,
            {"llm_call_id": "c1", "messages": [{"content": "abcd" * 5}, "not-a-dict"]},
        ),
    )
    await llm_event_sink(
        "fact_extractor",
        RuntimeEvent(
            RuntimeEventType.LLM_RESPONSE,
            {"llm_call_id": "c1", "response": "xyzw" * 7},
        ),
    )
    memory.memory_diagnostics = {"memory_write_status": dict(DEFAULT_WRITE_STATUS)}


def install_writer(monkeypatch, finalize=None):
    created: dict = {}

    class _Writer:
        def __init__(self, **kwargs):
            created["kwargs"] = kwargs

        async def finalize(self, *, memory, **kwargs):
            created["finalize_kwargs"] = {"memory": memory, **kwargs}
            impl = finalize or _default_writer_finalize
            await impl(memory, created["kwargs"]["llm_event_sink"])

    monkeypatch.setattr(tasks_memory, "MemoryWriter", _Writer)
    return created


def patch_finalize_common(monkeypatch, sessions):
    monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_stack(*sessions))
    monkeypatch.setattr("app.core.di.get_llm_client", Mock(return_value=object()))

    class _RoleService:
        def __init__(self, _session):
            pass

        async def get_role_config(self, role_type):
            return {"prompt": f"prompt-{role_type.value}"}

    monkeypatch.setattr(tasks_memory, "SystemLLMRoleService", _RoleService)


def make_outbox_row(payload, **over):
    now = datetime.now(timezone.utc)
    base = dict(
        id=uuid.uuid4(),
        runtime_run_id="run-1",
        chat_turn_id=None,
        payload=payload,
        status="pending",
        attempts=0,
        available_at=now,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestDisabledTasks:
    @pytest.mark.parametrize(
        "task,args",
        [
            (tasks_memory.reextract_stale_document_memory, ()),
            (tasks_memory.index_memory_items, ([str(uuid.uuid4())],)),
            (tasks_memory.rebuild_memory_index, ()),
            (tasks_memory.reconcile_memory_index, ()),
        ],
    )
    def test_returns_disabled(self, task, args):
        assert task.run(*args) == {"status": "disabled", "reason": "native_hipporag_document_corpus"}


class TestRemoveMemoryItems:
    def test_hipporag_backend_is_noop(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.get_settings",
            lambda: SimpleNamespace(MEMORY_SEARCH_BACKEND="hipporag"),
        )
        result = tasks_memory.remove_memory_items.run([str(uuid.uuid4())])
        assert result == {"removed": 0, "backend": "hipporag", "invalidated_by_read_policy": True}

    def test_semantic_backend_removes_items(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.config.get_settings",
            lambda: SimpleNamespace(MEMORY_SEARCH_BACKEND="qdrant"),
        )
        session = FakeSession()
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))
        captured: dict = {}

        class _Index:
            def __init__(self, sess):
                captured["session"] = sess

            async def remove_items(self, ids):
                captured["ids"] = ids
                return 3

        monkeypatch.setattr("app.runtime.memory.semantic_index.MemorySemanticIndex", _Index)

        id1, id2 = uuid.uuid4(), uuid.uuid4()
        assert tasks_memory.remove_memory_items.run([str(id1), str(id2)]) == {"removed": 3}
        assert captured["ids"] == [id1, id2]
        assert captured["session"] is session


class TestRefreshMemoryFreshness:
    def test_marks_stale_items_and_dispatches_removal(self, monkeypatch):
        now = datetime.now(timezone.utc)
        old_procedure = SimpleNamespace(
            id=uuid.uuid4(),
            item_type="procedure",
            state="active",
            last_verified_at=now - timedelta(days=100),
            updated_at=now,
        )
        fresh_description = SimpleNamespace(
            id=uuid.uuid4(),
            item_type="description",
            state="active",
            last_verified_at=None,
            updated_at=now - timedelta(days=200),
        )
        unknown_type = SimpleNamespace(
            id=uuid.uuid4(),
            item_type="weird",
            state="uncertain",
            last_verified_at=now - timedelta(days=400),
            updated_at=now - timedelta(days=400),
        )
        session = FakeSession()
        session.queue_select(
            tasks_memory.MemoryItem, [old_procedure, fresh_description, unknown_type]
        )
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))
        remove = SimpleNamespace(delay=Mock())
        monkeypatch.setattr(tasks_memory, "remove_memory_items", remove)

        result = tasks_memory.refresh_memory_freshness.run()
        assert result == {"stale": 2}
        assert old_procedure.state == "stale"
        assert unknown_type.state == "stale"
        assert fresh_description.state == "active"
        remove.delay.assert_called_once_with(
            [str(old_procedure.id), str(unknown_type.id)]
        )
        session.commit.assert_awaited_once()


class TestReconcileCollectionMemoryPolicy:
    def test_collection_not_found(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))
        result = tasks_memory.reconcile_collection_memory_policy.run(str(uuid.uuid4()))
        assert result == {"processed": 0, "reason": "collection_not_found"}

    def test_reconciles_rows(self, monkeypatch):
        from app.models.rag import RAGDocument

        collection_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        collection = SimpleNamespace(id=collection_id)
        doc1 = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id)
        doc2 = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id)
        doc3 = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id)
        doc4 = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id)
        src1 = SimpleNamespace(source_id=doc1.id, tenant_id=tenant_id)
        src2 = SimpleNamespace(source_id=doc2.id, tenant_id=tenant_id)
        src3 = SimpleNamespace(source_id=doc3.id, tenant_id=tenant_id)
        src4 = SimpleNamespace(source_id=doc4.id, tenant_id=tenant_id)

        current1 = SimpleNamespace(
            id=doc1.id, tenant_id=tenant_id, s3_key_processed="key-1", status="ready"
        )
        current4 = SimpleNamespace(id=doc4.id, tenant_id=tenant_id, s3_key_processed=None, status="archived")

        session = FakeSession()
        session.get_map[(tasks_memory.Collection, collection_id)] = collection
        session.queue_select(
            tasks_memory.Source, [(src1, doc1), (src2, doc2), (src3, doc3), (src4, doc4)]
        )
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))

        policy_results = [(True, current1), None, (False, doc3), (True, current4)]
        reconcile_calls = []

        class _MetadataService:
            def __init__(self, _session):
                pass

            async def reconcile_collection_policy(self, source_id, tenant):
                reconcile_calls.append((source_id, tenant))
                return policy_results.pop(0)

        monkeypatch.setattr(
            "app.services.document_source_metadata_service.DocumentSourceMetadataService",
            _MetadataService,
        )

        stale_item, active_item, uncertain_item = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        retire = AsyncMock(
            return_value={stale_item: "stale", active_item: "active", uncertain_item: "uncertain"}
        )
        monkeypatch.setattr(
            "app.runtime.memory.document_retirement.retire_document_memory", retire
        )

        remove = SimpleNamespace(delay=Mock())
        index = SimpleNamespace(delay=Mock())
        hipporag = SimpleNamespace(delay=Mock())
        monkeypatch.setattr(tasks_memory, "remove_memory_items", remove)
        monkeypatch.setattr(tasks_memory, "index_memory_items", index)
        monkeypatch.setattr(
            "app.workers.tasks_shadow_document_memory.hipporag_study_rag_document", hipporag
        )

        result = tasks_memory.reconcile_collection_memory_policy.run(str(collection_id))

        assert result == {"processed": 4, "enabled": 1}
        assert reconcile_calls == [
            (doc1.id, tenant_id),
            (doc2.id, tenant_id),
            (doc3.id, tenant_id),
            (doc4.id, tenant_id),
        ]
        retire.assert_awaited_once()
        assert retire.await_args.kwargs["document_id"] == doc3.id
        remove.delay.assert_called_once_with([str(stale_item)])
        indexed = index.delay.call_args[0][0]
        assert set(indexed) == {str(active_item), str(uncertain_item)}
        hipporag.delay.assert_called_once_with(
            {"source_id": str(doc1.id), "canonical_key": "key-1"}, str(tenant_id)
        )
        # One commit per processed (non-skipped) row.
        assert session.commit.await_count == 3
        assert session.commit.await_args_list[0].args == ()


class TestCompactChatContext:
    def test_invalid_payload_raises(self):
        with pytest.raises(ValidationError):
            tasks_memory.compact_chat_context.run({"chat_id": "not-enough"})

    def test_skips_when_no_operations(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr("app.core.di.reset_llm_client", Mock())
        monkeypatch.setattr("app.core.di.get_llm_client", Mock(return_value=object()))
        propose = AsyncMock(return_value=[])

        class _Compactor:
            def __init__(self, *, session, llm_client):
                pass

            async def propose(self, **kwargs):
                return await propose(**kwargs)

        monkeypatch.setattr(tasks_memory, "ChatContextCompactor", _Compactor)
        record = Mock()
        monkeypatch.setattr(
            "app.core.prometheus_metrics.record_chat_context_reconciliation", record
        )

        payload = {
            "chat_id": str(uuid.uuid4()),
            "chat_turn_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "expected_revision": 3,
            "snapshot": {"scope": "chat"},
        }
        assert tasks_memory.compact_chat_context.run(payload) == {
            "status": "skipped",
            "reason": "no_valid_operations",
        }
        record.assert_called_once_with(origin="compactor", outcome="no_op")

    def test_applies_compaction(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))
        llm = object()
        monkeypatch.setattr("app.core.di.reset_llm_client", Mock())
        monkeypatch.setattr("app.core.di.get_llm_client", Mock(return_value=llm))
        propose = AsyncMock(return_value=[{"op": "drop"}])
        service_instances = []

        class _Compactor:
            def __init__(self, *, session, llm_client):
                service_instances.append(("compactor", session, llm_client))

            async def propose(self, **kwargs):
                return await propose(**kwargs)

        apply_compaction = AsyncMock(
            return_value=SimpleNamespace(
                revision=7, applied_count=2, skipped_count=1, degradation_codes=["d"]
            )
        )

        class _Service:
            def __init__(self, sess, client, recorder):
                service_instances.append(("service", sess, client, recorder))

            async def apply_compaction(self, **kwargs):
                return await apply_compaction(**kwargs)

        monkeypatch.setattr(tasks_memory, "ChatContextCompactor", _Compactor)
        monkeypatch.setattr(tasks_memory, "ChatContextService", _Service)
        wt = passthrough_transaction()
        monkeypatch.setattr(tasks_memory, "worker_transaction", wt)

        chat_id = str(uuid.uuid4())
        branch_id = str(uuid.uuid4())
        payload = {
            "chat_id": chat_id,
            "chat_turn_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "expected_revision": 3,
            "snapshot": {"scope": "chat"},
            "sandbox_branch_id": branch_id,
        }
        result = tasks_memory.compact_chat_context.run(payload)
        assert result == {
            "status": "completed",
            "revision": 7,
            "applied": 2,
            "skipped": 1,
            "degraded": ["d"],
        }
        assert service_instances[0] == ("compactor", session, llm)
        assert service_instances[1] == ("service", session, llm, None)
        assert apply_compaction.await_args.kwargs == {
            "chat_id": chat_id,
            "branch_id": branch_id,
            "chat_turn_id": payload["chat_turn_id"],
            "expected_revision": 3,
            "operations": [{"op": "drop"}],
            "tenant_id": payload["tenant_id"],
        }


    # FIXME(known issue): `evaluate_memory_rag_evidence` crashes with
    # UnboundLocalError whenever a payload passes the evidence/items/claims
    # guard. The nested `_evaluate()` helper references `RAGDocument` at the
    # visible-claims query but re-imports it inside the reextract branch
    # (`from app.models.rag import RAGDocument`), which makes the name a local
    # variable for the entire function scope. Every evaluation path past the
    # early return is therefore unreachable at runtime. Reported as a
    # production defect; asserting the current behavior here.
    def test_valid_payload_crashes_on_shadowed_rag_document_import(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))

        with pytest.raises(UnboundLocalError, match="RAGDocument"):
            tasks_memory.evaluate_memory_rag_evidence.run(
                {
                    "tenant_id": str(uuid.uuid4()),
                    "tool_call_id": "tc",
                    "evidence": ["e1"],
                    "memory_item_ids": [str(uuid.uuid4())],
                    "claim_ids": [str(uuid.uuid4())],
                }
            )


class TestEvaluateMemoryRagEvidence:
    def test_no_evidence_returns_early(self, monkeypatch):
        result = tasks_memory.evaluate_memory_rag_evidence.run(
            {
                "tenant_id": str(uuid.uuid4()),
                "tool_call_id": "tc",
                "evidence": [],
                "memory_item_ids": [str(uuid.uuid4())],
                "claim_ids": [str(uuid.uuid4())],
            }
        )
        assert result == {"evaluated": 0, "reason": "no_evidence_or_items"}

    def test_legacy_result_fallback_uses_bounded_evidence(self, monkeypatch):
        bounded = Mock(return_value=["b1"])
        monkeypatch.setattr(tasks_memory, "bounded_document_evidence", bounded)
        raw_result = {"chunks": ["x"]}
        result = tasks_memory.evaluate_memory_rag_evidence.run(
            {"tenant_id": str(uuid.uuid4()), "tool_call_id": "tc", "result": raw_result}
        )
        bounded.assert_called_once_with(raw_result)
        assert result == {"evaluated": 0, "reason": "no_evidence_or_items"}


class TestDeserializeTurnMemory:
    def test_requires_chat_id(self):
        payload = MemoryFinalizePayload.model_validate(
            finalize_payload_dict(chat_id=None, summary={"chat_id": ""})
        )
        with pytest.raises(ValueError, match="chat_id is required"):
            _deserialize_turn_memory(payload)

    def test_falls_back_to_summary_chat_id(self):
        chat_id = str(uuid.uuid4())
        payload = MemoryFinalizePayload.model_validate(
            finalize_payload_dict(chat_id=None, summary={"chat_id": chat_id})
        )
        memory = _deserialize_turn_memory(payload)
        assert memory.chat_id == uuid.UUID(chat_id)

    def test_reconstructs_turn_memory(self):
        chat_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())
        payload = MemoryFinalizePayload.model_validate(
            finalize_payload_dict(
                chat_id=chat_id,
                user_id=user_id,
                tenant_id=tenant_id,
                retrieved_facts=[
                    {
                        "scope": "tenant",
                        "subject": "s",
                        "value": "v",
                        "source": "USER_UTTERANCE",
                        "tenant_id": tenant_id,
                        "confidence": 0.5,
                    }
                ],
            )
        )
        memory = _deserialize_turn_memory(payload)

        assert memory.chat_id == uuid.UUID(chat_id)
        assert memory.user_id == uuid.UUID(user_id)
        assert memory.tenant_id == uuid.UUID(tenant_id)
        assert memory.turn_number == 3
        assert memory.summary.chat_id == uuid.UUID(chat_id)
        assert memory.summary.goals == ["g"]
        assert len(memory.retrieved_facts) == 1
        fact = memory.retrieved_facts[0]
        assert fact.scope == FactScope.TENANT
        assert fact.source == FactSource.USER_UTTERANCE
        assert fact.tenant_id == uuid.UUID(tenant_id)
        assert fact.confidence == 0.5
        assert memory.agent_results[0].agent == "a1"
        assert memory.fact_evidence[0].source_id == "sid"
        assert memory.preflight_candidates == [{"subject": "p"}]
        assert memory.fact_run_ref == "run-1"


class TestLoadMemoryPrompts:
    async def test_loads_both_prompts(self, monkeypatch):
        from app.models.system_llm_role import SystemLLMRoleType

        class _RoleService:
            def __init__(self, session):
                self._session = session

            async def get_role_config(self, role_type):
                if role_type == SystemLLMRoleType.FACT_EXTRACTOR:
                    return {"prompt": "p-extract"}
                return {"prompt": "p-compact"}

        monkeypatch.setattr(tasks_memory, "SystemLLMRoleService", _RoleService)
        prompts = await _load_memory_prompts("session")
        assert prompts == {"fact_extractor": "p-extract", "fact_compactor": "p-compact"}

    async def test_failures_fall_back_to_empty_prompt(self, monkeypatch):
        from app.models.system_llm_role import SystemLLMRoleType

        class _RoleService:
            def __init__(self, _session):
                pass

            async def get_role_config(self, role_type):
                if role_type == SystemLLMRoleType.FACT_EXTRACTOR:
                    raise RuntimeError("db down")
                return {"prompt": None}

        monkeypatch.setattr(tasks_memory, "SystemLLMRoleService", _RoleService)
        prompts = await _load_memory_prompts(None)
        assert prompts == {"fact_extractor": "", "fact_compactor": ""}


class TestFinalizeMemoryTask:
    def test_missing_outbox(self, monkeypatch):
        guard = FakeSession()
        patch_finalize_common(monkeypatch, [guard])
        install_writer(monkeypatch)

        result = tasks_memory.finalize_memory_task.run({"outbox_id": str(uuid.uuid4())})
        assert result == {"status": "missing_outbox"}

    def test_already_completed_outbox(self, monkeypatch):
        row = make_outbox_row(finalize_payload_dict(), status="completed")
        guard = FakeSession()
        guard.queue_select(tasks_memory.MemoryFinalizeOutbox, [row])
        patch_finalize_common(monkeypatch, [guard])
        install_writer(monkeypatch)

        result = tasks_memory.finalize_memory_task.run({"outbox_id": str(row.id)})
        assert result == {"status": "already_completed"}

    def test_fresh_running_outbox_short_circuits(self, monkeypatch):
        row = make_outbox_row(
            finalize_payload_dict(),
            status="running",
            updated_at=datetime.now(timezone.utc),
        )
        guard = FakeSession()
        guard.queue_select(tasks_memory.MemoryFinalizeOutbox, [row])
        patch_finalize_common(monkeypatch, [guard])
        install_writer(monkeypatch)

        result = tasks_memory.finalize_memory_task.run({"outbox_id": str(row.id)})
        assert result == {"status": "already_running"}
        assert row.attempts == 0

    def test_stale_running_outbox_proceeds_and_completes(self, monkeypatch):
        row = make_outbox_row(
            finalize_payload_dict(),
            status="running",
            attempts=2,
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=45),
            last_error="old",
        )
        guard = FakeSession()
        guard.queue_select(tasks_memory.MemoryFinalizeOutbox, [row])
        completion = FakeSession()
        completion.queue_select(tasks_memory.MemoryFinalizeOutbox, [row])
        main = FakeSession()
        patch_finalize_common(monkeypatch, [guard, main, completion])
        writer = install_writer(monkeypatch)
        checkpoint = AsyncMock()
        monkeypatch.setattr(tasks_memory, "checkpoint_commit", checkpoint)

        result = tasks_memory.finalize_memory_task.run({"outbox_id": str(row.id)})

        assert result["status"] == "ok"
        assert row.status == "completed"
        assert row.attempts == 3
        assert row.last_error is None
        guard.commit.assert_awaited_once()
        completion.commit.assert_awaited_once()
        checkpoint.assert_awaited_once_with(main, "finalize_memory", "facts_writeback")
        assert writer["finalize_kwargs"]["memory"].chat_id == uuid.UUID(
            row.payload["chat_id"]
        )

    def test_happy_path_without_outbox(self, monkeypatch):
        main = FakeSession()
        patch_finalize_common(monkeypatch, [main])
        writer = install_writer(monkeypatch)
        checkpoint = AsyncMock()
        monkeypatch.setattr(tasks_memory, "checkpoint_commit", checkpoint)

        payload_dict = finalize_payload_dict(runtime_run_id="run-9")
        result = tasks_memory.finalize_memory_task.run(payload_dict)

        assert result["status"] == "ok"
        assert result["chat_id"] == payload_dict["chat_id"]
        assert result["turn_number"] == 3
        assert [c["component_name"] for c in result["components"]] == [
            "fact_extractor",
            "fact_compactor",
        ]
        assert result["failed"] == ["fact_compactor"]
        assert result["degraded"] == []

        kwargs = writer["kwargs"]
        assert kwargs["session"] is main
        assert set(kwargs["component_execution_ids"]) == {"fact_extractor", "fact_compactor"}
        assert callable(kwargs["llm_event_sink"])
        finalize_kwargs = writer["finalize_kwargs"]
        assert finalize_kwargs["user_message"] == "hello"
        assert finalize_kwargs["assistant_final"] == "hi"
        assert finalize_kwargs["terminal_reason"] is None
        assert finalize_kwargs["sandbox_overrides"] is None
        assert finalize_kwargs["memory"].fact_run_ref == "run-9"
        checkpoint.assert_awaited_once()

    def test_runtime_logger_receives_events_with_tail_id(self, monkeypatch):
        recorder = SimpleNamespace(append_runtime_event=AsyncMock())
        restore = Mock(return_value=recorder)
        monkeypatch.setattr(
            tasks_memory.RuntimeEventJournalFactory,
            "restore_worker",
            restore,
        )
        main = FakeSession()
        patch_finalize_common(monkeypatch, [main])
        install_writer(monkeypatch)

        payload_dict = finalize_payload_dict(
            runtime_log_context={"journal_id": "j1"},
            tail_id="tail-1",
            terminal_reason="totally_bogus_reason",
        )
        result = tasks_memory.finalize_memory_task.run(payload_dict)

        assert result["status"] == "ok"
        restore.assert_called_once_with({"journal_id": "j1"})
        events = [call.args[0] for call in recorder.append_runtime_event.await_args_list]
        assert events
        assert all(event.data.get("tail_id") == "tail-1" for event in events)
        stages = [event.data.get("stage") for event in events]
        assert "memory_write_end" in stages
        assert "tail_finished" in stages
        assert "orchestrator_start" in [event.type.value for event in events]
        # LLM token accounting: request 20 chars -> 5 tokens in, response 28 -> 7 out.
        response_events = [
            event for event in events if event.type.value == "llm_response"
        ]
        assert response_events[0].data["tokens_in"] == 5
        assert response_events[0].data["tokens_out"] == 7
        assert response_events[0].data["tokens_total"] == 12
        budget_events = [event for event in events if event.type.value == "budget_snapshot"]
        assert any(event.data.get("reason") == "finalize" for event in budget_events)

    def test_writer_failure_releases_outbox_and_retries(self, monkeypatch):
        async def failing_finalize(memory, sink):
            raise RuntimeError("writer boom")

        row = make_outbox_row(finalize_payload_dict())
        guard = FakeSession()
        guard.queue_select(tasks_memory.MemoryFinalizeOutbox, [row])
        release = FakeSession()
        release.queue_select(tasks_memory.MemoryFinalizeOutbox, [row])
        main = FakeSession()
        patch_finalize_common(monkeypatch, [guard, main, release])
        install_writer(monkeypatch, finalize=failing_finalize)

        before = datetime.now(timezone.utc)
        with pytest.raises(RuntimeError, match="writer boom"):
            tasks_memory.finalize_memory_task.run({"outbox_id": str(row.id)})

        assert row.status == "pending"
        assert row.last_error is not None and row.last_error.startswith("writer boom")
        assert abs((row.available_at - (before + timedelta(seconds=60))).total_seconds()) < 10
        release.commit.assert_awaited_once()

    def test_invalid_payload_without_outbox_raises_validation_error(self, monkeypatch):
        patch_finalize_common(monkeypatch, [])
        install_writer(monkeypatch)

        with pytest.raises(ValidationError):
            tasks_memory.finalize_memory_task.run({"turn_number": "not-an-int"})

    def test_inline_task_delegates_to_finalize_memory_task(self, monkeypatch):
        delegate = Mock(return_value={"status": "ok"})
        monkeypatch.setattr(tasks_memory, "finalize_memory_task", SimpleNamespace(run=delegate))

        payload = finalize_payload_dict()
        assert tasks_memory.finalize_memory_inline_task.run(payload) == {"status": "ok"}
        delegate.assert_called_once()
        assert delegate.call_args.args[0] == tasks_memory.finalize_memory_inline_task
        assert delegate.call_args.args[1] is payload


class TestReconcileMemoryFinalizeOutbox:
    def _row(self, **over):
        now = datetime.now(timezone.utc)
        base = dict(
            id=uuid.uuid4(),
            runtime_run_id=str(uuid.uuid4()),
            chat_turn_id=None,
            payload={},
            status="pending",
            attempts=0,
            available_at=now,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        base.update(over)
        return SimpleNamespace(**base)

    def test_dispatch_matrix(self, monkeypatch):
        from app.models.chat_turn import ChatTurn

        r1 = self._row(status="pending")  # no chat_turn -> dispatched
        r2 = self._row(status="dispatched", chat_turn_id=uuid.uuid4())  # turn missing -> discarded
        r3 = self._row(status="dispatched", chat_turn_id=uuid.uuid4())  # turn cancelled -> discarded
        r4 = self._row(status="running", chat_turn_id=uuid.uuid4())  # turn running -> skipped
        r5 = self._row(status="pending", chat_turn_id=uuid.uuid4())  # completed w/o assistant message -> skipped
        r6 = self._row(status="running", chat_turn_id=uuid.uuid4())  # failed with assistant message -> dispatched

        session = FakeSession()
        session.queue_select(tasks_memory.MemoryFinalizeOutbox, [r1, r2, r3, r4, r5, r6])
        session.get_map[(ChatTurn, r2.chat_turn_id)] = None
        for row, turn in (
            (r3, SimpleNamespace(status="cancelled", assistant_message_id=uuid.uuid4())),
            (r4, SimpleNamespace(status="running", assistant_message_id=None)),
            (r5, SimpleNamespace(status="completed", assistant_message_id=None)),
            (r6, SimpleNamespace(status="failed", assistant_message_id=uuid.uuid4())),
        ):
            session.get_map[(ChatTurn, row.chat_turn_id)] = turn
        monkeypatch.setattr(tasks_memory, "get_worker_session", make_session_scope(session))
        apply_async = Mock()
        monkeypatch.setattr(
            tasks_memory, "finalize_memory_task", SimpleNamespace(apply_async=apply_async)
        )

        result = tasks_memory.reconcile_memory_finalize_outbox.run()

        assert result == {"dispatched": 2, "discarded": 2}
        assert r1.status == "dispatched"
        assert r2.status == "discarded"
        assert r3.status == "discarded"
        assert r4.status == "running"
        assert r5.status == "pending"
        assert r6.status == "dispatched"
        session.commit.assert_awaited_once()
        assert apply_async.call_count == 2
        first = apply_async.call_args_list[0]
        assert first.args == ()
        assert first.kwargs == {
            "args": [{"outbox_id": str(r1.id)}],
            "task_id": f"memory-finalize-{r1.id}",
        }

    def test_broker_failure_returns_row_to_pending(self, monkeypatch):
        row = self._row(status="pending")
        session = FakeSession()
        session.queue_select(tasks_memory.MemoryFinalizeOutbox, [row])
        fallback = FakeSession()
        fallback.get_map[(tasks_memory.MemoryFinalizeOutbox, row.id)] = row
        monkeypatch.setattr(
            tasks_memory, "get_worker_session", make_session_stack(session, fallback)
        )

        def failing_apply_async(**_kwargs):
            raise RuntimeError("broker down")

        monkeypatch.setattr(
            tasks_memory,
            "finalize_memory_task",
            SimpleNamespace(apply_async=failing_apply_async),
        )

        before = datetime.now(timezone.utc)
        result = tasks_memory.reconcile_memory_finalize_outbox.run()

        assert result == {"dispatched": 0, "discarded": 0}
        assert row.status == "pending"
        assert row.last_error is not None and "broker down" in row.last_error
        assert abs((row.available_at - (before + timedelta(seconds=60))).total_seconds()) < 10
        fallback.commit.assert_awaited_once()
