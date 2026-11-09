from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.sandbox import runs
from app.services import sandbox_result_browser as browser


@pytest.mark.asyncio
async def test_result_scope_requires_matching_session_and_recorded_tenant(monkeypatch):
    session_id, run_id, owner, tenant = (uuid4() for _ in range(4))
    svc = SimpleNamespace(get_run=AsyncMock(return_value=SimpleNamespace(session_id=session_id)))
    monkeypatch.setattr(runs, "SandboxService", lambda db: svc)
    check = AsyncMock()
    monkeypatch.setattr(runs, "check_session_owner", check)
    db = SimpleNamespace(scalar=AsyncMock(return_value=tenant))
    user = SimpleNamespace(id=str(owner))
    assert await runs._result_scope(db, user, session_id, run_id) == {
        "run_id": str(run_id), "tenant_id": tenant, "user_id": owner,
    }
    check.assert_awaited_once_with(svc, session_id, user)
    svc.get_run.return_value = SimpleNamespace(session_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        await runs._result_scope(db, user, session_id, run_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_read_page_limits_bytes_and_preserves_revision(monkeypatch):
    metadata = {"result_id": str(uuid4()), "revision": 2, "row_count": 3}
    results = [
        SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: metadata)),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [6, 6, 6])),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [{"x": 1}])),
    ]
    connection = SimpleNamespace(execute=AsyncMock(side_effect=results))

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(browser, "get_tool_results_engine", lambda: SimpleNamespace(begin=transaction))
    monkeypatch.setattr(browser, "MAX_PAGE_BYTES", 10)
    page = await browser.SandboxResultBrowser().read_page(
        run_id=str(uuid4()), user_id=uuid4(), tenant_id=uuid4(), result_id=uuid4(),
        offset=0, limit=3, revision=2,
    )
    assert page["rows"] == [{"x": 1}]
    assert page["next_offset"] == 1
    assert connection.execute.await_args_list[2].args[1]["limit"] == 1


@pytest.mark.asyncio
async def test_read_page_rejects_changed_revision_before_reading_rows(monkeypatch):
    metadata = {"revision": 3}
    connection = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        mappings=lambda: SimpleNamespace(first=lambda: metadata))))

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(browser, "get_tool_results_engine", lambda: SimpleNamespace(begin=transaction))
    with pytest.raises(ValueError, match="revision changed"):
        await browser.SandboxResultBrowser().read_page(
            run_id=str(uuid4()), user_id=uuid4(), tenant_id=uuid4(), result_id=uuid4(),
            offset=0, limit=20, revision=2,
        )
    assert connection.execute.await_count == 1


@pytest.mark.asyncio
async def test_read_page_rejects_a_row_that_cannot_fit(monkeypatch):
    metadata = {"revision": 1, "row_count": 1}
    connection = SimpleNamespace(execute=AsyncMock(side_effect=[
        SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: metadata)),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [11])),
    ]))

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(browser, "get_tool_results_engine", lambda: SimpleNamespace(begin=transaction))
    monkeypatch.setattr(browser, "MAX_PAGE_BYTES", 10)
    with pytest.raises(browser.ResultRowTooLarge):
        await browser.SandboxResultBrowser().read_page(
            run_id=str(uuid4()), user_id=uuid4(), tenant_id=uuid4(), result_id=uuid4(),
            offset=0, limit=20, revision=None,
        )
    assert connection.execute.await_count == 2


@pytest.mark.asyncio
async def test_result_scope_rejects_missing_journal_scope(monkeypatch):
    session_id = uuid4()
    svc = SimpleNamespace(get_run=AsyncMock(return_value=SimpleNamespace(session_id=session_id)))
    monkeypatch.setattr(runs, "SandboxService", lambda db: svc)
    monkeypatch.setattr(runs, "check_session_owner", AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await runs._result_scope(SimpleNamespace(scalar=AsyncMock(return_value=None)),
                                 SimpleNamespace(id=str(uuid4())), session_id, uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_metadata_endpoint_uses_authorized_scope_and_handles_missing(monkeypatch):
    session_id, run_id, result_id, user_id, tenant_id = (uuid4() for _ in range(5))
    scope = {"run_id": str(run_id), "user_id": user_id, "tenant_id": tenant_id}
    monkeypatch.setattr(runs, "_result_scope", AsyncMock(return_value=scope))
    service = SimpleNamespace(get_metadata=AsyncMock(return_value={"result_id": str(result_id)}))
    monkeypatch.setattr(runs, "SandboxResultBrowser", lambda: service)
    assert await runs.get_run_result_metadata(session_id, run_id, result_id, db=None, user=None) == {"result_id": str(result_id)}
    service.get_metadata.assert_awaited_once_with(**scope, result_id=result_id)
    service.get_metadata.return_value = None
    with pytest.raises(HTTPException) as exc:
        await runs.get_run_result_metadata(session_id, run_id, result_id, db=None, user=None)
    assert exc.value.status_code == 404
