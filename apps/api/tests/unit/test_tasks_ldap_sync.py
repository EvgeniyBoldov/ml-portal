"""Unit tests for app/workers/tasks_ldap_sync.py."""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from app.workers import tasks_ldap_sync


@pytest.fixture(autouse=True)
def restore_ldap_metrics():
    snapshot = dict(tasks_ldap_sync._ldap_metrics)
    yield
    tasks_ldap_sync._ldap_metrics.clear()
    tasks_ldap_sync._ldap_metrics.update(snapshot)


def make_session_scope(session, calls=None):
    @asynccontextmanager
    async def scope():
        if calls is not None:
            calls.append(session)
        yield session

    return scope


def ldap_settings(*, enabled=True, sync_enabled=True) -> SimpleNamespace:
    return SimpleNamespace(AUTH_LDAP_ENABLED=enabled, AUTH_LDAP_SYNC_ENABLED=sync_enabled)


def install_settings(monkeypatch, settings) -> None:
    monkeypatch.setattr(tasks_ldap_sync, "get_settings", lambda: settings)


def install_ldap_client(monkeypatch, health=None, *, side_effect=None) -> list:
    created: list = []

    class FakeLDAPClient:
        def __init__(self, settings_arg) -> None:
            created.append(settings_arg)
            if side_effect is not None:
                self.health_check = AsyncMock(side_effect=side_effect)
            else:
                self.health_check = AsyncMock(return_value=health)

    monkeypatch.setattr(tasks_ldap_sync, "LDAPClient", FakeLDAPClient)
    return created


def install_ldap_service(monkeypatch, sync_mock) -> list:
    created: list = []

    class FakeLDAPUserService:
        def __init__(self, session_arg, settings_arg) -> None:
            created.append((session_arg, settings_arg))
            self.sync_user_status = sync_mock

    monkeypatch.setattr(tasks_ldap_sync, "LDAPUserService", FakeLDAPUserService)
    return created


def install_users_repo(monkeypatch, users) -> list:
    instances: list = []

    class FakeUsersRepository:
        def __init__(self, session_arg) -> None:
            self.list_by_auth_provider = AsyncMock(return_value=users)
            instances.append(self)

    monkeypatch.setattr("app.repositories.users_repo.AsyncUsersRepository", FakeUsersRepository)
    return instances


def install_retry(monkeypatch, task) -> list:
    attempts: list = []

    def retry(exc=None, **_kwargs):
        attempts.append(exc)
        raise exc

    monkeypatch.setattr(task, "retry", retry)
    return attempts


# ---------------------------------------------------------------------------
# get_ldap_metrics
# ---------------------------------------------------------------------------


def test_get_ldap_metrics_returns_copy():
    tasks_ldap_sync._ldap_metrics["users_total"] = 5

    metrics = tasks_ldap_sync.get_ldap_metrics()

    assert metrics == tasks_ldap_sync._ldap_metrics
    metrics["users_total"] = 999
    assert tasks_ldap_sync._ldap_metrics["users_total"] == 5


# ---------------------------------------------------------------------------
# sync_ldap_users
# ---------------------------------------------------------------------------


def test_sync_ldap_users_skips_when_ldap_disabled(monkeypatch):
    session = SimpleNamespace(commit=AsyncMock())
    scope_calls: list = []
    before = tasks_ldap_sync.get_ldap_metrics()
    install_settings(monkeypatch, ldap_settings(enabled=False))
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session, scope_calls))

    result = tasks_ldap_sync.sync_ldap_users.run()

    assert result == {"status": "skipped", "reason": "ldap_not_enabled"}
    assert scope_calls == []
    assert session.commit.assert_not_awaited() is None
    assert tasks_ldap_sync.get_ldap_metrics() == before


def test_sync_ldap_users_skips_when_sync_disabled(monkeypatch):
    session = SimpleNamespace(commit=AsyncMock())
    scope_calls: list = []
    before = tasks_ldap_sync.get_ldap_metrics()
    install_settings(monkeypatch, ldap_settings(sync_enabled=False))
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session, scope_calls))

    result = tasks_ldap_sync.sync_ldap_users.run()

    assert result == {"status": "skipped", "reason": "sync_disabled"}
    assert scope_calls == []
    assert tasks_ldap_sync.get_ldap_metrics() == before


def test_sync_ldap_users_retries_when_ldap_unreachable(monkeypatch):
    settings = ldap_settings()
    session = SimpleNamespace(commit=AsyncMock())
    before = tasks_ldap_sync.get_ldap_metrics()
    install_settings(monkeypatch, settings)
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session))
    clients = install_ldap_client(monkeypatch, health={"reachable": False, "error": "no route"})
    services = install_ldap_service(monkeypatch, AsyncMock())
    repos = install_users_repo(monkeypatch, [])
    attempts = install_retry(monkeypatch, tasks_ldap_sync.sync_ldap_users)

    with pytest.raises(Exception, match="LDAP not reachable: no route"):
        tasks_ldap_sync.sync_ldap_users.run()

    assert len(attempts) == 1
    assert str(attempts[0]) == "LDAP not reachable: no route"
    assert clients == [settings]

    after = tasks_ldap_sync.get_ldap_metrics()
    assert after["ldap_up"] == 0
    # FIXME(known issue): an unreachable LDAP server double-counts errors_total —
    # once inside _do_sync (health check branch) and again in the outer
    # `except Exception` handler.
    assert after["errors_total"] == before["errors_total"] + 2
    assert after["last_run_timestamp"] > 0
    assert after["last_success_timestamp"] == before["last_success_timestamp"]

    # The user list is never queried and nothing is committed.
    assert repos == []
    assert services[0][0] is session
    assert services[0][1] is settings
    session.commit.assert_not_awaited()


def test_sync_ldap_users_returns_error_after_retries_exhausted(monkeypatch):
    session = SimpleNamespace(commit=AsyncMock())
    before = tasks_ldap_sync.get_ldap_metrics()
    install_settings(monkeypatch, ldap_settings())
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session))
    install_ldap_client(monkeypatch, health={"reachable": False, "error": "timeout"})
    monkeypatch.setattr(tasks_ldap_sync.sync_ldap_users, "max_retries", 0)

    result = tasks_ldap_sync.sync_ldap_users.run()

    assert result["status"] == "error"
    assert result["error"] == "LDAP not reachable: timeout"
    assert result["processed"] == 0
    assert result["errors"] == 0
    # FIXME(known issue): errors_total is double-counted for an unreachable
    # server (health-check branch + outer except handler).
    assert tasks_ldap_sync.get_ldap_metrics()["errors_total"] == before["errors_total"] + 2


def test_sync_ldap_users_syncs_all_users_and_counts_actions(monkeypatch):
    users = [SimpleNamespace(login=f"u{i}") for i in range(1, 7)]
    sync = AsyncMock(
        side_effect=[
            {"action": "deactivated", "reason": "ldap_not_found"},
            {"action": "deactivated", "reason": "ldap_disabled"},
            {"action": "reactivated"},
            {"action": "updated"},
            {"action": "skipped"},
            RuntimeError("boom"),
        ]
    )
    session = SimpleNamespace(commit=AsyncMock())
    before = tasks_ldap_sync.get_ldap_metrics()
    install_settings(monkeypatch, ldap_settings())
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session))
    install_ldap_client(monkeypatch, health={"reachable": True, "status": "healthy"})
    install_ldap_service(monkeypatch, sync)
    repos = install_users_repo(monkeypatch, users)

    result = tasks_ldap_sync.sync_ldap_users.run()

    assert result["status"] == "success"
    assert isinstance(result["duration_seconds"], float)
    assert result["processed"] == 5
    assert result["deactivated_not_found"] == 1
    assert result["deactivated_disabled"] == 1
    assert result["reactivated"] == 1
    assert result["profile_updated"] == 1
    assert result["skipped"] == 1
    assert result["errors"] == 1

    assert [call.args[0] for call in sync.await_args_list] == users
    assert len(repos) == 1
    repos[0].list_by_auth_provider.assert_awaited_once_with("ldap")
    session.commit.assert_awaited_once()

    after = tasks_ldap_sync.get_ldap_metrics()
    assert after["users_total"] == 6
    assert after["users_deactivated"] == 2
    assert after["ldap_up"] == 1
    assert after["errors_total"] == before["errors_total"] + 1
    assert after["last_success_timestamp"] >= after["last_run_timestamp"] > 0


def test_sync_ldap_users_reraises_soft_time_limit_from_health_check(monkeypatch):
    session = SimpleNamespace(commit=AsyncMock())
    before = tasks_ldap_sync.get_ldap_metrics()
    install_settings(monkeypatch, ldap_settings())
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session))
    install_ldap_client(monkeypatch, side_effect=SoftTimeLimitExceeded("deadline"))
    attempts = install_retry(monkeypatch, tasks_ldap_sync.sync_ldap_users)

    with pytest.raises(SoftTimeLimitExceeded):
        tasks_ldap_sync.sync_ldap_users.run()

    # The dedicated handler re-raises without scheduling a retry.
    assert attempts == []
    after = tasks_ldap_sync.get_ldap_metrics()
    assert after["errors_total"] == before["errors_total"] + 1
    assert after["last_success_timestamp"] == before["last_success_timestamp"]
    session.commit.assert_not_awaited()


def test_sync_ldap_users_swallows_soft_time_limit_raised_per_user(monkeypatch):
    # FIXME(known issue): SoftTimeLimitExceeded inherits from Exception, so the
    # broad per-user ``except Exception`` in sync_ldap_users treats the celery
    # soft time limit as an ordinary user-level failure and keeps processing
    # instead of aborting the whole task. Only a limit hit outside the user
    # loop reaches the dedicated outer handler.
    users = [SimpleNamespace(login="u1"), SimpleNamespace(login="u2")]
    sync = AsyncMock(side_effect=[SoftTimeLimitExceeded("deadline"), {"action": "updated"}])
    session = SimpleNamespace(commit=AsyncMock())
    install_settings(monkeypatch, ldap_settings())
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session))
    install_ldap_client(monkeypatch, health={"reachable": True, "status": "healthy"})
    install_ldap_service(monkeypatch, sync)
    install_users_repo(monkeypatch, users)

    result = tasks_ldap_sync.sync_ldap_users.run()

    assert result["status"] == "success"
    assert result["processed"] == 1
    assert result["profile_updated"] == 1
    assert result["errors"] == 1


# ---------------------------------------------------------------------------
# ldap_health_check
# ---------------------------------------------------------------------------


def test_ldap_health_check_reports_disabled(monkeypatch):
    before = tasks_ldap_sync.get_ldap_metrics()
    before["ldap_up"] = 1
    tasks_ldap_sync._ldap_metrics["ldap_up"] = 1
    scope_calls: list = []
    session = SimpleNamespace(commit=AsyncMock())
    install_settings(monkeypatch, ldap_settings(enabled=False))
    monkeypatch.setattr(tasks_ldap_sync, "get_worker_session", make_session_scope(session, scope_calls))
    clients = install_ldap_client(monkeypatch, health={"reachable": True, "status": "healthy"})

    result = tasks_ldap_sync.ldap_health_check.run()

    assert result == {"status": "disabled", "reachable": False}
    assert tasks_ldap_sync.get_ldap_metrics()["ldap_up"] == 0
    assert clients == []
    assert scope_calls == []


def test_ldap_health_check_marks_ldap_up_when_healthy(monkeypatch):
    install_settings(monkeypatch, ldap_settings())
    install_ldap_client(monkeypatch, health={"reachable": True, "status": "healthy", "server": "ldap://ad"})

    result = tasks_ldap_sync.ldap_health_check.run()

    assert result == {"reachable": True, "status": "healthy", "server": "ldap://ad"}
    assert tasks_ldap_sync.get_ldap_metrics()["ldap_up"] == 1


def test_ldap_health_check_marks_ldap_down_when_degraded(monkeypatch):
    install_settings(monkeypatch, ldap_settings())
    install_ldap_client(monkeypatch, health={"reachable": True, "status": "slow", "error": "high latency"})

    result = tasks_ldap_sync.ldap_health_check.run()

    assert result == {"reachable": True, "status": "slow", "error": "high latency"}
    assert tasks_ldap_sync.get_ldap_metrics()["ldap_up"] == 0


def test_ldap_health_check_retries_on_exception(monkeypatch):
    install_settings(monkeypatch, ldap_settings())
    install_ldap_client(monkeypatch, side_effect=RuntimeError("conn refused"))
    attempts = install_retry(monkeypatch, tasks_ldap_sync.ldap_health_check)

    with pytest.raises(RuntimeError, match="conn refused"):
        tasks_ldap_sync.ldap_health_check.run()

    assert len(attempts) == 1
    assert tasks_ldap_sync.get_ldap_metrics()["ldap_up"] == 0


def test_ldap_health_check_returns_error_after_retries_exhausted(monkeypatch):
    install_settings(monkeypatch, ldap_settings())
    install_ldap_client(monkeypatch, side_effect=RuntimeError("conn refused"))
    monkeypatch.setattr(tasks_ldap_sync.ldap_health_check, "max_retries", 0)

    result = tasks_ldap_sync.ldap_health_check.run()

    assert result == {"status": "error", "reachable": False, "error": "conn refused"}
    assert tasks_ldap_sync.get_ldap_metrics()["ldap_up"] == 0
