"""Unit tests for app/workers/tasks_health.py."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Select, Update

from app.services.health import BACKOFF_POLICY_1M, BACKOFF_POLICY_10M
from app.workers import tasks_health


class RowResult:
    """Result stub supporting direct iteration (snapshot selects)."""

    def __init__(self, rows: list) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class ScalarsResult:
    """Result stub supporting .scalars().all()."""

    def __init__(self, items: list) -> None:
        self._items = items

    def scalars(self):
        return SimpleNamespace(all=lambda: self._items)


def make_session(result=None) -> SimpleNamespace:
    execute = AsyncMock(return_value=result) if result is not None else AsyncMock()
    return SimpleNamespace(execute=execute, commit=AsyncMock())


def make_session_scope(session: SimpleNamespace):
    @asynccontextmanager
    async def scope():
        yield session

    return scope


def make_health_result(healthy: bool) -> SimpleNamespace:
    return SimpleNamespace(is_healthy=lambda: healthy)


def install_locks(monkeypatch, *, acquired: bool = True) -> AsyncMock:
    acquire = AsyncMock(return_value=acquired)
    release = AsyncMock()
    monkeypatch.setattr(tasks_health, "acquire_advisory_lock", acquire)
    monkeypatch.setattr(tasks_health, "release_advisory_lock", release)
    return release


def make_engine_factory():
    """Return (engine_factory, engines) where engines collects created instances."""
    engines: list = []

    class FakeEngine:
        def __init__(self, session) -> None:
            self.session = session
            self.registrations: list = []
            self.check_tool_instances_kwargs = None
            self.check_models_kwargs = None
            engines.append(self)

        def register_adapter(self, key, adapter, policy) -> None:
            self.registrations.append((key, type(adapter).__name__, policy))

        async def check_tool_instances(self, **kwargs):
            self.check_tool_instances_kwargs = kwargs
            return self.tool_results

        async def check_models(self, **kwargs):
            self.check_models_kwargs = kwargs
            return self.model_results

    return FakeEngine, engines


ALL_PROBE_TASKS = [
    tasks_health.probe_mcp_connectors,
    tasks_health.probe_data_connectors,
    tasks_health.probe_embedding_models,
    tasks_health.probe_rerank_models,
    tasks_health.probe_llm_models,
    tasks_health.rescan_discovery,
]


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------


def test_get_lock_key_is_deterministic_and_positive():
    first = tasks_health.get_lock_key("probe_mcp_connectors")

    assert first == tasks_health.get_lock_key("probe_mcp_connectors")
    assert 0 <= first <= 0x7FFFFFFF
    assert first != tasks_health.get_lock_key("rescan_discovery")


async def test_acquire_advisory_lock_returns_scalar_result():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: True)))

    assert await tasks_health.acquire_advisory_lock(session, 42) is True
    stmt = session.execute.await_args.args[0]
    assert "pg_try_advisory_lock" in str(stmt)
    assert session.execute.await_args.args[1] == {"lock_key": 42}


async def test_acquire_advisory_lock_returns_false_on_error():
    session = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("db down")))

    assert await tasks_health.acquire_advisory_lock(session, 42) is False


async def test_release_advisory_lock_returns_scalar_result():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar=lambda: False)))

    assert await tasks_health.release_advisory_lock(session, 7) is False
    stmt = session.execute.await_args.args[0]
    assert "pg_advisory_unlock" in str(stmt)


async def test_release_advisory_lock_returns_false_on_error():
    session = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("db down")))

    assert await tasks_health.release_advisory_lock(session, 7) is False


@pytest.mark.parametrize("task", ALL_PROBE_TASKS, ids=lambda task: task.name)
def test_probe_tasks_skip_when_lock_is_held(monkeypatch, task):
    session = make_session()

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    release = install_locks(monkeypatch, acquired=False)

    assert task.run() == {"status": "skipped", "reason": "locked"}
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    # The locked branch returns before the try/finally, so the lock that was
    # never acquired is also never released.
    release.assert_not_awaited()


# ---------------------------------------------------------------------------
# probe_mcp_connectors
# ---------------------------------------------------------------------------


def test_probe_mcp_connectors_summarizes_results(monkeypatch):
    snapshot_rows = [
        SimpleNamespace(id="inst-1", health_status="healthy"),
        SimpleNamespace(id="inst-2", health_status=None),
    ]
    session = make_session(result=RowResult(snapshot_rows))
    results = {
        "inst-1": make_health_result(False),
        "inst-2": make_health_result(True),
    }
    engine_factory, engines = make_engine_factory()
    engine_factory.tool_results = results  # type: ignore[attr-defined]
    transitions = AsyncMock()

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    install_locks(monkeypatch)
    monkeypatch.setattr(tasks_health, "HealthCheckEngine", engine_factory)
    monkeypatch.setattr(tasks_health, "_process_mcp_health_transitions", transitions)

    summary = tasks_health.probe_mcp_connectors.run()

    assert summary["status"] == "completed"
    assert summary["checked"] == 2
    assert summary["healthy"] == 1
    assert summary["unhealthy"] == 1
    assert summary["timestamp"]

    engine = engines[0]
    assert engine.session is session
    assert engine.registrations == [("mcp_connector", "MCPHealthAdapter", BACKOFF_POLICY_1M)]
    assert engine.check_tool_instances_kwargs == {"connector_type": "mcp", "limit": 50}

    transitions.assert_awaited_once()
    call_session, call_results, call_previous = transitions.await_args.args
    assert call_session is session
    assert call_results is results
    assert call_previous == {"inst-1": "healthy", "inst-2": "unknown"}

    session.commit.assert_awaited_once()


def test_probe_mcp_connectors_propagates_engine_errors(monkeypatch):
    session = make_session(result=RowResult([]))
    engine_factory, _engines = make_engine_factory()

    async def fail(*args, **kwargs):
        raise RuntimeError("engine exploded")

    engine_factory.check_tool_instances = fail  # type: ignore[attr-defined]

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    release = install_locks(monkeypatch)
    monkeypatch.setattr(tasks_health, "HealthCheckEngine", engine_factory)

    with pytest.raises(RuntimeError, match="engine exploded"):
        tasks_health.probe_mcp_connectors.run()
    release.assert_awaited_once()
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# probe_data_connectors
# ---------------------------------------------------------------------------


def test_probe_data_connectors_with_no_instances(monkeypatch):
    session = make_session(result=ScalarsResult([]))
    created_sessions: list = []

    class FakeToolInstanceService:
        def __init__(self, session_arg) -> None:
            created_sessions.append(session_arg)

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    install_locks(monkeypatch)
    monkeypatch.setattr("app.services.tool_instance_service.ToolInstanceService", FakeToolInstanceService)

    summary = tasks_health.probe_data_connectors.run()

    assert summary == {"status": "completed", "checked": 0}
    assert created_sessions == []
    session.commit.assert_not_awaited()


def test_probe_data_connectors_counts_mixed_outcomes(monkeypatch):
    instances = [
        SimpleNamespace(id="data-1"),
        SimpleNamespace(id="data-2"),
        SimpleNamespace(id="data-3"),
    ]
    session = make_session(result=ScalarsResult(instances))
    created_sessions: list = []
    checks = AsyncMock(
        side_effect=[
            SimpleNamespace(status="healthy"),
            SimpleNamespace(status="unreachable"),
            RuntimeError("connection refused"),
        ]
    )

    class FakeToolInstanceService:
        def __init__(self, session_arg) -> None:
            created_sessions.append(session_arg)
            self.health = SimpleNamespace(check_health=checks)

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    install_locks(monkeypatch)
    monkeypatch.setattr("app.services.tool_instance_service.ToolInstanceService", FakeToolInstanceService)

    summary = tasks_health.probe_data_connectors.run()

    assert created_sessions == [session]
    assert summary["status"] == "completed"
    assert summary["checked"] == 3
    assert summary["healthy"] == 1
    assert summary["unhealthy"] == 2
    assert summary["timestamp"]
    checks.assert_awaited_with("data-3")
    assert [call.args for call in checks.await_args_list] == [("data-1",), ("data-2",), ("data-3",)]
    session.commit.assert_awaited_once()


def test_probe_data_connectors_propagates_query_errors(monkeypatch):
    session = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("select failed")), commit=AsyncMock())

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    release = install_locks(monkeypatch)

    with pytest.raises(RuntimeError, match="select failed"):
        tasks_health.probe_data_connectors.run()
    release.assert_awaited_once()


# ---------------------------------------------------------------------------
# probe_embedding_models / probe_rerank_models / probe_llm_models
# ---------------------------------------------------------------------------


def run_model_probe(monkeypatch, task, *, adapter_key, adapter_class, policy, model_type, limit):
    session = make_session()
    results = {
        "model-1": make_health_result(True),
        "model-2": make_health_result(True),
        "model-3": make_health_result(False),
    }
    engine_factory, engines = make_engine_factory()
    engine_factory.model_results = results  # type: ignore[attr-defined]

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    install_locks(monkeypatch)
    monkeypatch.setattr(tasks_health, "HealthCheckEngine", engine_factory)

    summary = task.run()

    engine = engines[0]
    assert engine.registrations == [(adapter_key, adapter_class, policy)]
    assert engine.check_models_kwargs == {"model_type": model_type, "limit": limit}
    assert summary["status"] == "completed"
    assert summary["checked"] == 3
    assert summary["healthy"] == 2
    assert summary["unhealthy"] == 1
    session.commit.assert_awaited_once()
    return summary


def test_probe_embedding_models_registers_adapter_and_summarizes(monkeypatch):
    summary = run_model_probe(
        monkeypatch,
        tasks_health.probe_embedding_models,
        adapter_key="embedding_model",
        adapter_class="EmbeddingHealthAdapter",
        policy=BACKOFF_POLICY_1M,
        model_type="embedding",
        limit=20,
    )
    assert summary["timestamp"]


def test_probe_rerank_models_registers_adapter_and_summarizes(monkeypatch):
    run_model_probe(
        monkeypatch,
        tasks_health.probe_rerank_models,
        adapter_key="reranker_model",
        adapter_class="RerankHealthAdapter",
        policy=BACKOFF_POLICY_1M,
        model_type="reranker",
        limit=10,
    )


def test_probe_llm_models_registers_adapter_and_summarizes(monkeypatch):
    run_model_probe(
        monkeypatch,
        tasks_health.probe_llm_models,
        adapter_key="llm_chat_model",
        adapter_class="LLMHealthAdapter",
        policy=BACKOFF_POLICY_10M,
        model_type="llm_chat",
        limit=10,
    )


@pytest.mark.parametrize(
    "task",
    [
        tasks_health.probe_embedding_models,
        tasks_health.probe_rerank_models,
        tasks_health.probe_llm_models,
    ],
    ids=lambda task: task.name,
)
def test_model_probes_propagate_engine_errors(monkeypatch, task):
    session = make_session()
    engine_factory, _engines = make_engine_factory()

    async def fail(*args, **kwargs):
        raise RuntimeError("model check failed")

    engine_factory.check_models = fail  # type: ignore[attr-defined]

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    release = install_locks(monkeypatch)
    monkeypatch.setattr(tasks_health, "HealthCheckEngine", engine_factory)

    with pytest.raises(RuntimeError, match="model check failed"):
        task.run()
    release.assert_awaited_once()
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# rescan_discovery
# ---------------------------------------------------------------------------


def test_rescan_discovery_reports_successful_scans(monkeypatch):
    instance = SimpleNamespace(id="provider-1", slug="mcp_sql")
    session = make_session(result=ScalarsResult([instance]))
    service = SimpleNamespace(
        rescan=AsyncMock(return_value={"mcp_upserted": 3, "marked_inactive": 1}),
    )
    created_sessions: list = []

    class FakeDiscoveryService:
        def __init__(self, session_arg) -> None:
            created_sessions.append(session_arg)
            self.rescan = service.rescan

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    install_locks(monkeypatch)
    monkeypatch.setattr(tasks_health, "ToolDiscoveryService", FakeDiscoveryService)

    summary = tasks_health.rescan_discovery.run()

    assert created_sessions == [session]
    service.rescan.assert_awaited_once_with(include_local=False, provider_instance_id="provider-1")
    assert summary["providers_scanned"] == 1
    assert summary["successful_scans"] == 1
    assert summary["failed_scans"] == 0
    assert summary["total_tools_found"] == 3
    assert summary["total_tools_updated"] == 3
    assert summary["total_tools_removed"] == 1
    assert summary["details"] == [
        {
            "instance_id": "provider-1",
            "slug": "mcp_sql",
            "tools_found": 3,
            "tools_updated": 3,
            "tools_removed": 1,
            "scan_meta": {"mcp_upserted": 3, "marked_inactive": 1},
            "success": True,
        }
    ]
    session.commit.assert_awaited_once()


def test_rescan_discovery_records_provider_exceptions(monkeypatch):
    instance = SimpleNamespace(id="provider-1", slug="mcp_sql")
    session = make_session(result=ScalarsResult([instance]))
    service = SimpleNamespace(rescan=AsyncMock(side_effect=RuntimeError("provider offline")))

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    install_locks(monkeypatch)
    monkeypatch.setattr(tasks_health, "ToolDiscoveryService", lambda _session: service)

    summary = tasks_health.rescan_discovery.run()

    assert summary["providers_scanned"] == 1
    assert summary["successful_scans"] == 0
    assert summary["failed_scans"] == 1
    assert summary["total_tools_found"] == 0
    assert summary["details"][0]["error"] == "provider offline"
    assert summary["details"][0]["success"] is False
    session.commit.assert_awaited_once()


def test_rescan_discovery_propagates_unexpected_errors(monkeypatch):
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=RuntimeError("pool exhausted")),
        commit=AsyncMock(),
    )

    monkeypatch.setattr(tasks_health, "get_worker_session", make_session_scope(session))
    release = install_locks(monkeypatch)

    with pytest.raises(RuntimeError, match="pool exhausted"):
        tasks_health.rescan_discovery.run()
    release.assert_awaited_once()
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# _process_mcp_health_transitions and helpers
# ---------------------------------------------------------------------------


class TransitionScript:
    """Fake session replaying transition flow: select instance, then updates."""

    def __init__(self, instance) -> None:
        self.instance = instance
        self.executed: list = []
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, stmt):
        self.executed.append(stmt)
        if isinstance(stmt, Update):
            return SimpleNamespace()
        assert isinstance(stmt, Select), f"unexpected statement {stmt!r}"
        return SimpleNamespace(scalar_one_or_none=lambda: self.instance)


def transition_instance(instance_id) -> SimpleNamespace:
    return SimpleNamespace(id=instance_id, slug="mcp_sql")


async def test_transition_healthy_to_unhealthy_invalidates_discovered_tools():
    instance_id = uuid.uuid4()
    session = TransitionScript(transition_instance(instance_id))
    results = {instance_id: make_health_result(False)}

    await tasks_health._process_mcp_health_transitions(
        session, results, {str(instance_id): "healthy"}
    )

    assert len(session.executed) == 2
    select_stmt, update_stmt = session.executed
    assert isinstance(select_stmt, Select)
    assert isinstance(update_stmt, Update)
    assert update_stmt.table.name == "discovered_tools"
    params = update_stmt.compile().params
    assert params["is_active"] is False
    assert str(instance_id) in [str(value) for value in params.values()]


async def test_transition_unhealthy_to_healthy_schedules_rescan():
    instance_id = uuid.uuid4()
    session = TransitionScript(transition_instance(instance_id))
    results = {instance_id: make_health_result(True)}

    await tasks_health._process_mcp_health_transitions(
        session, results, {str(instance_id): "unhealthy"}
    )

    assert len(session.executed) == 2
    update_stmt = session.executed[1]
    assert isinstance(update_stmt, Update)
    assert update_stmt.table.name == "tool_instances"
    params = update_stmt.compile().params
    assert isinstance(params.get("next_check_at"), datetime)
    assert str(instance_id) in [str(value) for value in params.values()]


async def test_transition_without_change_does_not_write():
    instance_id = uuid.uuid4()
    session = TransitionScript(transition_instance(instance_id))
    results = {instance_id: make_health_result(True)}

    await tasks_health._process_mcp_health_transitions(
        session, results, {str(instance_id): "healthy"}
    )

    assert len(session.executed) == 1


async def test_transition_skips_unknown_instance():
    session = TransitionScript(None)

    await tasks_health._process_mcp_health_transitions(
        session, {"missing": make_health_result(True)}, {"missing": "unhealthy"}
    )

    assert len(session.executed) == 1


async def test_transition_swallows_query_errors():
    session = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("db down")))

    # Must not raise: per-instance failures are logged and skipped.
    await tasks_health._process_mcp_health_transitions(
        session, {"inst-1": make_health_result(True)}, {"inst-1": "unhealthy"}
    )
    session.execute.assert_awaited_once()


async def test_invalidate_discovered_tools_deactivates_rows():
    session = make_session()
    instance_id = uuid.uuid4()

    await tasks_health._invalidate_discovered_tools(session, instance_id)

    stmt = session.execute.await_args.args[0]
    assert isinstance(stmt, Update)
    assert stmt.table.name == "discovered_tools"
    params = stmt.compile().params
    assert params["is_active"] is False
    assert str(instance_id) in [str(value) for value in params.values()]


async def test_schedule_discovery_rescan_updates_next_check_at():
    session = make_session()
    instance = SimpleNamespace(id=uuid.uuid4(), slug="mcp_sql")

    await tasks_health._schedule_discovery_rescan(session, instance)

    stmt = session.execute.await_args.args[0]
    assert isinstance(stmt, Update)
    assert stmt.table.name == "tool_instances"
    params = stmt.compile().params
    assert isinstance(params.get("next_check_at"), datetime)
    assert str(instance.id) in [str(value) for value in params.values()]
