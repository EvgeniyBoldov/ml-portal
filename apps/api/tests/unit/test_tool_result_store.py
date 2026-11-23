"""Unit tests for ToolResultStore persistence, catalog, import and analysis paths."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest

import app.services.tool_result_store as store_module
from app.core.config import get_settings
from app.services.tool_result_store import (
    ResultSnapshotUnavailable,
    ToolResultStore,
    ToolResultStoreError,
    _combine_completeness,
    _json_dumps_exact,
    _json_values_equal,
    _path_segments,
    _response_value_budget,
    _source_total,
    create_tool_results_engine,
    dispose_tool_results_engine,
    get_tool_results_engine,
    sql_ref_for_result,
)


class FakeMappingsResult:
    def __init__(
        self,
        first: Any = None,
        one: Any = None,
        rows: list | None = None,
        scalar: Any = None,
        scalar_one: Any = None,
    ) -> None:
        self._first, self._one = first, one
        self._rows = rows or []
        self._scalar, self._scalar_one = scalar, scalar_one

    def mappings(self) -> FakeMappingsResult:
        return self

    def first(self) -> Any:
        return self._first

    def one(self) -> Any:
        return self._one

    def all(self) -> list:
        return self._rows

    def scalar(self) -> Any:
        return self._scalar

    def scalar_one(self) -> Any:
        return self._scalar_one

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class ConnectionContext:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def __aenter__(self) -> Any:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def connect(self) -> ConnectionContext:
        return ConnectionContext(self._connection)

    def begin(self) -> ConnectionContext:
        return ConnectionContext(self._connection)


def patch_engine(monkeypatch: pytest.MonkeyPatch, connection: Any) -> None:
    monkeypatch.setattr(store_module, "get_tool_results_engine", lambda: FakeEngine(connection))


def forbid_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise AssertionError("engine must not be used")

    monkeypatch.setattr(store_module, "get_tool_results_engine", boom)


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------


class FakeInspectResult:
    def __init__(self, description: list) -> None:
        self.cursor = SimpleNamespace(description=description)


class FakeSaveConnection:
    """Connection fake dispatching on the raw statements issued by save()."""

    def __init__(
        self,
        *,
        existing: dict | None = None,
        returning: dict | None = None,
        page_payload: Any = None,
        description: list | None = None,
    ) -> None:
        self.existing = existing
        self.returning = returning
        self.page_payload = page_payload
        self.description = description or []
        self.calls: list[tuple[str, Any]] = []
        self.row_batches: list[list[dict]] = []
        self.insert_params: dict | None = None

    async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
        rendered = str(statement)
        self.calls.append((rendered, params))
        if "FOR UPDATE" in rendered:
            return FakeMappingsResult(first=self.existing)
        if "SELECT payload FROM runtime_tool_result_pages" in rendered:
            return FakeMappingsResult(scalar=self.page_payload)
        if "INSERT INTO runtime_tool_payloads" in rendered:
            self.insert_params = dict(params)
            return FakeMappingsResult(one=self.returning)
        if "LIMIT 0" in rendered:
            return FakeInspectResult(self.description)  # type: ignore[return-value]
        if isinstance(params, list):
            self.row_batches.append(list(params))
        return FakeMappingsResult()


@pytest.mark.asyncio
async def test_save_insert_persists_rows_schema_and_source_page(monkeypatch: pytest.MonkeyPatch) -> None:
    result_id = UUID("d51f0000-0000-4000-8000-000000000010")
    connection = FakeSaveConnection(
        returning={"result_id": str(result_id), "result_uuid": result_id, "revision": 1},
        description=[("a", 1700), ("b", 25)],
    )
    patch_engine(monkeypatch, connection)
    payload = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    source_page = {
        "page_key": "page-1",
        "source_tool": "generic.tool",
        "arguments": {"offset": 0},
        "value": ["a", "b"],
        "payload": ["a", "b"],
        "meta": {"total": 2},
    }

    result = await ToolResultStore().save(
        run_id="run-1", call_id="call-1", operation="generic.tool",
        tenant_id=uuid4(), user_id=uuid4(), task_id="task-1", agent_execution_id=None,
        payload=payload, source_result_ids=[], arguments={"q": 1}, source_page=source_page,
    )

    serialized = _json_dumps_exact(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    assert result["result_id"] == str(result_id)
    assert result["sql_ref"] == sql_ref_for_result(str(result_id))
    assert result["row_count"] == 2
    assert result["revision"] == 1
    assert result["inline_complete"] is True
    assert connection.insert_params["payload_sha256"] == hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    assert connection.insert_params["operation"] == "generic.tool"
    assert result["dataset_meta"]["table_schema"]["a"]["type"] == "numeric"
    assert result["dataset_meta"]["table_schema"]["b"]["type"] == "text"
    # Dataset rows were re-written via executemany with stable ordinals.
    assert len(connection.row_batches) == 1
    assert [row["ordinal"] for row in connection.row_batches[0]] == [0, 1]
    # The dataset_meta update targets the inserted row.
    update = [call for call in connection.calls if "UPDATE runtime_tool_payloads SET dataset_meta" in call[0]]
    assert update and update[0][1]["id"] == result_id
    # The source page is recorded for idempotency checks.
    page = [call for call in connection.calls if "INSERT INTO runtime_tool_result_pages" in call[0]]
    assert page and page[0][1]["key"] == "page-1"


@pytest.mark.asyncio
async def test_save_returns_existing_result_for_equal_source_page(monkeypatch: pytest.MonkeyPatch) -> None:
    result_uuid = UUID("d51f0000-0000-4000-8000-000000000011")
    existing = {
        "result_id": str(result_uuid), "result_uuid": result_uuid, "operation": "generic.tool",
        "payload": {"value": ["a", "b"]}, "payload_sha256": "sha", "source_total": 2,
        "source_complete": True, "observed_schema": {"a": {}}, "sample": None,
        "sample_complete": True, "schema_complete": True, "row_count": 2,
        "query_sql": None, "source_result_ids": [], "dataset_meta": {"total": 2}, "revision": 2,
    }
    connection = FakeSaveConnection(existing=existing, page_payload=["a", "b"])
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().save(
        run_id="run-1", call_id="call-1", operation="generic.tool",
        tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
        payload=["a", "b"],
        source_page={"page_key": "page-1", "source_tool": "generic.tool", "arguments": {},
                     "value": ["a", "b"], "payload": ["a", "b"], "meta": {}},
    )

    assert result["result_id"] == existing["result_id"]
    assert result["revision"] == 2
    assert result["dataset_meta"] == {"total": 2}
    # A replayed page on a multi-revision result is never inlined.
    assert result["inline_complete"] is False
    assert not any(
        rendered.startswith(("INSERT", "UPDATE", "DELETE")) for rendered, _ in connection.calls
    )


def _existing_row(operation: str = "generic.tool") -> dict:
    result_uuid = UUID("d51f0000-0000-4000-8000-000000000012")
    return {
        "result_id": str(result_uuid), "result_uuid": result_uuid, "operation": operation,
        "payload": {"value": ["a"]}, "payload_sha256": "old-sha", "source_total": 1,
        "source_complete": True, "observed_schema": {}, "sample": None,
        "sample_complete": True, "schema_complete": True, "row_count": 1,
        "query_sql": None, "source_result_ids": [], "dataset_meta": {}, "revision": 1,
    }


@pytest.mark.asyncio
async def test_save_wraps_operation_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeSaveConnection(existing=_existing_row(operation="other.tool"))
    patch_engine(monkeypatch, connection)
    with pytest.raises(ToolResultStoreError, match="Could not persist tool result"):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-1", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload={"value": ["a"]},
        )


@pytest.mark.asyncio
async def test_save_wraps_payload_mismatch_without_source_page(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeSaveConnection(existing=_existing_row())
    patch_engine(monkeypatch, connection)
    with pytest.raises(ToolResultStoreError, match="Could not persist tool result"):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-1", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload={"value": ["different"]},
        )


@pytest.mark.asyncio
async def test_save_wraps_unknown_source_page_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeSaveConnection(existing=_existing_row(), page_payload=None)
    patch_engine(monkeypatch, connection)
    with pytest.raises(ToolResultStoreError, match="Could not persist tool result"):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-1", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload={"value": ["a"]},
            source_page={"page_key": "page-9", "source_tool": "generic.tool", "arguments": {},
                         "value": ["a"], "payload": ["a"], "meta": {}},
        )


@pytest.mark.asyncio
async def test_save_wraps_engine_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenConnection:
        async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
            raise RuntimeError("database unavailable")

    patch_engine(monkeypatch, BrokenConnection())
    with pytest.raises(ToolResultStoreError, match="Could not persist tool result"):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-1", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload={"ok": True},
        )


@pytest.mark.asyncio
async def test_save_rejects_unserializable_payload_before_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_engine(monkeypatch)
    # Tuple dict keys are rejected by json.dumps even with default=str (the hook
    # only covers values, not keys).
    with pytest.raises(ToolResultStoreError, match="Tool result is not JSON serializable"):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-1", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload={(1, 2): "value"},
        )
    with pytest.raises(ToolResultStoreError, match="Tool result is not JSON serializable"):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-2", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload={"bad": Decimal("NaN")},
        )


@pytest.mark.asyncio
async def test_save_self_referencing_payload_raises_recursion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # FIXME(known issue): a self-referencing payload makes _json_dumps_exact's
    # ``prepare`` recurse infinitely, so RecursionError escapes instead of the
    # intended "Tool result is not JSON serializable" wrap. Testing current
    # behavior; the wrapped error path is covered by the TypeError/ValueError
    # cases above.
    forbid_engine(monkeypatch)
    circular: dict[str, Any] = {}
    circular["self"] = circular
    with pytest.raises(RecursionError):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-1", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload=circular,
        )


@pytest.mark.asyncio
async def test_save_rejects_oversized_payload_before_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "TOOL_RESULTS_MAX_PAYLOAD_BYTES", 8)
    forbid_engine(monkeypatch)
    with pytest.raises(ToolResultStoreError, match="Tool result exceeds the configured storage limit"):
        await ToolResultStore().save(
            run_id="run-1", call_id="call-1", operation="generic.tool",
            tenant_id=uuid4(), user_id=uuid4(), task_id=None, agent_execution_id=None,
            payload={"a": "x" * 64},
        )


# ---------------------------------------------------------------------------
# list_for_run / list_prior_snapshots
# ---------------------------------------------------------------------------


class FakeListConnection:
    def __init__(self, rows: list | None = None, selected_rows: list | None = None, total: int = 0) -> None:
        self.rows = rows or []
        self.selected_rows = selected_rows or []
        self.total = total
        self.calls: list[tuple[str, Any]] = []

    async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
        rendered = str(statement)
        self.calls.append((rendered, params))
        if "count(*)" in rendered:
            return FakeMappingsResult(scalar_one=self.total)
        if " OR " in rendered:
            return FakeMappingsResult(rows=self.selected_rows)
        if "ORDER BY created_at" in rendered:
            # Honor the OFFSET/LIMIT parameters so pagination is realistic.
            query_params = params if isinstance(params, dict) else {}
            offset = int(query_params.get("offset", 0))
            limit = int(query_params.get("limit", len(self.rows)))
            return FakeMappingsResult(rows=self.rows[offset:offset + limit])
        return FakeMappingsResult(rows=self.rows)


@pytest.mark.asyncio
async def test_list_for_run_formats_catalog_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    result_id = "e62f0000-0000-4000-8000-000000000020"
    row = {
        "result_id": result_id, "operation": "generic.tool", "row_count": 3,
        "task_id": "task-1", "call_id": "call-1", "agent_execution_id": None,
        "payload_type": "array", "source_complete": True, "observed_schema": None,
        "sample": None, "sample_complete": False, "schema_complete": True,
        "query_sql": None, "source_result_ids": None, "dataset_meta": None,
        "revision": 1, "source_total": 3,
    }
    connection = FakeListConnection(rows=[row])
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().list_for_run(run_id="run-1", tenant_id=uuid4(), user_id=uuid4())

    assert len(result) == 1
    assert result[0]["sql_ref"] == sql_ref_for_result(result_id)
    assert result[0]["dataset_meta"] == {}
    assert result[0]["source_result_ids"] == []
    assert result[0]["row_count"] == 3
    assert connection.calls[0][1]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_list_for_run_reuses_caller_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_engine(monkeypatch)
    passed = FakeListConnection(rows=[{
        "result_id": "e62f0000-0000-4000-8000-000000000021", "operation": "op", "row_count": 0,
        "task_id": None, "call_id": "call-2", "agent_execution_id": None, "payload_type": "object",
        "source_complete": None, "observed_schema": {}, "sample": None, "sample_complete": True,
        "schema_complete": False, "query_sql": "SELECT 1", "source_result_ids": [], "dataset_meta": {},
        "revision": 2, "source_total": None,
    }])

    result = await ToolResultStore().list_for_run(
        run_id="run-1", tenant_id=uuid4(), user_id=uuid4(), connection=passed,  # type: ignore[arg-type]
    )

    assert result[0]["query_sql"] == "SELECT 1"
    assert result[0]["schema_complete"] is False
    assert len(passed.calls) == 1


def _snapshot_row(result_id: str, *, dataset_meta: dict | None = None) -> dict:
    return {
        "result_id": result_id, "run_id": "run-9", "operation": "collection.search",
        "task_id": "task-9", "row_count": 4, "payload_type": "array", "source_complete": True,
        "source_total": 4, "revision": 1,
        "created_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        "expires_at": datetime(2026, 1, 9, 3, 4, 5, tzinfo=timezone.utc),
        "dataset_meta": dataset_meta, "source_result_ids": None,
    }


@pytest.mark.asyncio
async def test_list_prior_snapshots_validates_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_engine(monkeypatch)
    store = ToolResultStore()
    for kwargs in ({"offset": -1}, {"limit": 0}, {"limit": 51}):
        with pytest.raises(ToolResultStoreError, match="Invalid snapshot catalog offset or limit"):
            await store.list_prior_snapshots(
                source_run_id="run-9", tenant_id=uuid4(), user_id=uuid4(), **kwargs
            )


@pytest.mark.asyncio
async def test_list_prior_snapshots_rejects_too_many_selected_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_engine(monkeypatch, FakeListConnection())
    with pytest.raises(ToolResultStoreError, match="At most 50 selected result IDs may be resolved"):
        await ToolResultStore().list_prior_snapshots(
            source_run_id="run-9", tenant_id=uuid4(), user_id=uuid4(),
            selected_result_ids=[str(uuid4()) for _ in range(51)],
        )


@pytest.mark.asyncio
async def test_list_prior_snapshots_browse_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_snapshot_row(str(uuid4())) for _ in range(3)]
    connection = FakeListConnection(rows=rows, total=3)
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().list_prior_snapshots(
        source_run_id="run-9", tenant_id=uuid4(), user_id=uuid4(), offset=0, limit=2,
    )

    assert result["total"] == 3
    assert len(result["items"]) == 2
    assert result["next_offset"] == 2
    assert result["catalog_complete"] is False
    item = result["items"][0]
    assert item["importable"] is True
    assert item["unavailable_reason"] is None
    assert item["created_at"] == "2026-01-02T03:04:05+00:00"
    assert item["producer"] == {"task_id": "task-9"}

    complete = await ToolResultStore().list_prior_snapshots(
        source_run_id="run-9", tenant_id=uuid4(), user_id=uuid4(), offset=2, limit=2,
    )
    assert complete["items"][0]["importable"] is True
    assert complete["next_offset"] is None
    assert complete["catalog_complete"] is True


@pytest.mark.asyncio
async def test_list_prior_snapshots_marks_file_controlled_rows_unimportable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _snapshot_row(str(uuid4()), dataset_meta={"source_operation": "file.read"})
    connection = FakeListConnection(rows=[row], total=1)
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().list_prior_snapshots(
        source_run_id="run-9", tenant_id=uuid4(), user_id=uuid4(),
    )

    assert result["items"][0]["importable"] is False
    assert result["items"][0]["unavailable_reason"] == "source_reauthorization_required"


@pytest.mark.asyncio
async def test_list_prior_snapshots_selected_mode_marks_missing_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known_id = str(uuid4())
    missing_id = str(uuid4())
    connection = FakeListConnection(selected_rows=[_snapshot_row(known_id)])
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().list_prior_snapshots(
        source_run_id="run-9", tenant_id=uuid4(), user_id=uuid4(),
        selected_result_ids=[known_id, "not-a-uuid", missing_id, known_id],
    )

    assert result["total"] == 3
    assert [item["result_id"] for item in result["items"]] == [known_id, "not-a-uuid", missing_id]
    assert result["items"][0]["importable"] is True
    for missing in result["items"][1:]:
        assert missing["importable"] is False
        assert missing["unavailable_reason"] == "snapshot_unavailable"
    assert result["next_offset"] is None


# ---------------------------------------------------------------------------
# import_snapshot()
# ---------------------------------------------------------------------------


class FakeImportConnection:
    def __init__(self, source: dict | None, existing: dict | None = None) -> None:
        self.source = source
        self.existing = existing
        self.calls: list[tuple[str, Any]] = []

    async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
        rendered = str(statement)
        self.calls.append((rendered, params))
        if "pg_advisory_xact_lock" in rendered:
            return FakeMappingsResult()
        if "FOR SHARE" in rendered:
            return FakeMappingsResult(first=self.source)
        if "call_id=:call_id" in rendered:
            return FakeMappingsResult(first=self.existing)
        return FakeMappingsResult()


def _source_row(result_id: str) -> dict:
    return {
        "result_id": result_id, "run_id": "run-1", "operation": "collection.search",
        "payload": {"rows": [1, 2]}, "payload_sha256": "sha-1", "source_total": 2,
        "source_complete": True, "observed_schema": None, "sample": None,
        "sample_complete": True, "schema_complete": True, "row_count": 2, "revision": 1,
        "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
        "expires_at": datetime(2026, 2, 8, tzinfo=timezone.utc),
        "dataset_meta": {"next_arguments": {"offset": 50}, "source_operation": "jira.search"},
        "source_result_ids": None,
    }


@pytest.mark.asyncio
async def test_import_snapshot_rejects_same_run_and_bad_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_engine(monkeypatch)
    store = ToolResultStore()
    with pytest.raises(ResultSnapshotUnavailable) as exc_info:
        await store.import_snapshot(
            source_run_id="run-1", source_result_id=str(uuid4()), source_revision=1,
            target_run_id="run-1", target_tenant_id=uuid4(), target_user_id=uuid4(),
        )
    assert exc_info.value.reason == "same_run_snapshot_import_forbidden"

    with pytest.raises(ResultSnapshotUnavailable) as exc_info:
        await store.import_snapshot(
            source_run_id="run-1", source_result_id="not-a-uuid", source_revision=1,
            target_run_id="run-2", target_tenant_id=uuid4(), target_user_id=uuid4(),
        )
    assert exc_info.value.reason == "snapshot_unavailable"


@pytest.mark.asyncio
async def test_import_snapshot_source_missing_and_revision_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ToolResultStore()
    connection = FakeImportConnection(source=None)
    patch_engine(monkeypatch, connection)
    with pytest.raises(ResultSnapshotUnavailable) as exc_info:
        await store.import_snapshot(
            source_run_id="run-1", source_result_id=str(uuid4()), source_revision=1,
            target_run_id="run-2", target_tenant_id=uuid4(), target_user_id=uuid4(),
        )
    assert exc_info.value.reason == "snapshot_unavailable"

    stale = dict(_source_row(str(uuid4())), revision=2)
    connection = FakeImportConnection(source=stale)
    patch_engine(monkeypatch, connection)
    with pytest.raises(ResultSnapshotUnavailable) as exc_info:
        await store.import_snapshot(
            source_run_id="run-1", source_result_id=stale["result_id"], source_revision=1,
            target_run_id="run-2", target_tenant_id=uuid4(), target_user_id=uuid4(),
        )
    assert exc_info.value.reason == "result_revision_conflict"


@pytest.mark.asyncio
async def test_import_snapshot_rejects_file_controlled_source(monkeypatch: pytest.MonkeyPatch) -> None:
    source = dict(_source_row(str(uuid4())), operation="file.read")
    connection = FakeImportConnection(source=source)
    patch_engine(monkeypatch, connection)
    with pytest.raises(ResultSnapshotUnavailable) as exc_info:
        await ToolResultStore().import_snapshot(
            source_run_id="run-1", source_result_id=source["result_id"], source_revision=1,
            target_run_id="run-2", target_tenant_id=uuid4(), target_user_id=uuid4(),
        )
    assert exc_info.value.reason == "source_reauthorization_required"


@pytest.mark.asyncio
async def test_import_snapshot_copies_source_atomically(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source_row("f73f0000-0000-4000-8000-000000000030")
    connection = FakeImportConnection(source=source)
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().import_snapshot(
        source_run_id="run-1", source_result_id=source["result_id"], source_revision=1,
        target_run_id="run-2", target_tenant_id=uuid4(), target_user_id=uuid4(),
        target_task_id="task-2",
    )

    expected_call_id = f"runtime-import:run-1:{source['result_id']}:1"
    expected_target = uuid5(NAMESPACE_URL, f"ml-portal-result:run-2:{expected_call_id}")
    assert result["result_id"] == str(expected_target)
    assert result["already_imported"] is False
    assert result["revision"] == 1
    assert result["snapshot_only"] is True
    assert result["row_count"] == 2
    assert result["imported_from"]["source_run_id"] == "run-1"
    assert result["imported_from"]["source_result_id"] == source["result_id"]
    assert result["imported_from"]["continuation_was_available"] is True
    assert result["imported_from"]["file_controlled"] is False
    assert result["dataset_meta"]["continuation_error"] == "Imported snapshots do not fetch additional source pages"
    insert = [call for call in connection.calls if "INSERT INTO runtime_tool_payloads" in call[0]]
    assert insert and insert[0][1]["call_id"] == expected_call_id
    copy = [call for call in connection.calls if "INSERT INTO runtime_tool_result_rows" in call[0]]
    assert copy and copy[0][1]["source_id"] == source["result_id"]


@pytest.mark.asyncio
async def test_import_snapshot_is_idempotent_for_matching_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    source_id = str(uuid4())
    source = _source_row(source_id)
    existing = {
        "result_id": str(uuid4()), "revision": 1, "source_total": 2, "source_complete": True,
        "row_count": 2, "payload": {"rows": [1, 2]}, "payload_sha256": "sha-1",
        "observed_schema": None, "sample": None, "sample_complete": True, "schema_complete": True,
        "dataset_meta": {"snapshot_only": True, "imported_from": {
            "source_run_id": "run-1", "source_result_id": source_id, "source_revision": 1,
        }},
        "expires_at": datetime(2026, 2, 8, tzinfo=timezone.utc),
    }
    connection = FakeImportConnection(source=source, existing=existing)
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().import_snapshot(
        source_run_id="run-1", source_result_id=source_id, source_revision=1,
        target_run_id="run-2", target_tenant_id=uuid4(), target_user_id=uuid4(),
    )

    assert result["already_imported"] is True
    assert result["result_id"] == existing["result_id"]
    assert result["snapshot_only"] is True
    assert not any("INSERT" in rendered for rendered, _ in connection.calls)


@pytest.mark.asyncio
async def test_import_snapshot_detects_idempotency_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _source_row(str(uuid4()))
    existing = {
        "result_id": str(uuid4()), "revision": 1, "source_total": 2, "source_complete": True,
        "row_count": 2, "payload": {"rows": [1, 2]}, "payload_sha256": "sha-1",
        "observed_schema": None, "sample": None, "sample_complete": True, "schema_complete": True,
        "dataset_meta": {"imported_from": {
            "source_run_id": "run-other", "source_result_id": str(uuid4()), "source_revision": 9,
        }},
        "expires_at": datetime(2026, 2, 8, tzinfo=timezone.utc),
    }
    connection = FakeImportConnection(source=source, existing=existing)
    patch_engine(monkeypatch, connection)

    with pytest.raises(ToolResultStoreError, match="Import idempotency key conflicts with another snapshot"):
        await ToolResultStore().import_snapshot(
            source_run_id="run-1", source_result_id=source["result_id"], source_revision=1,
            target_run_id="run-2", target_tenant_id=uuid4(), target_user_id=uuid4(),
        )


# ---------------------------------------------------------------------------
# _is_file_controlled_snapshot
# ---------------------------------------------------------------------------


class FakeLineageConnection:
    def __init__(self, sources: dict[tuple[str, str], dict | None]) -> None:
        self.sources = sources

    async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
        row = self.sources.get((params["id"], params["run_id"]))
        return FakeMappingsResult(first=row)


def _lineage_row(result_id: str, run_id: str, **meta: Any) -> dict:
    return {
        "result_id": result_id, "run_id": run_id, "operation": "collection.search",
        "dataset_meta": meta or None, "source_result_ids": [],
    }


@pytest.mark.asyncio
async def test_lineage_rejects_cycles_and_missing_parents() -> None:
    a, b = str(uuid4()), str(uuid4())
    sources = {
        (a, "run-1"): _lineage_row(a, "run-1", **{
            "imported_from": {"source_run_id": "run-2", "source_result_id": b, "source_revision": 1,
                              "source_operation": "collection.search", "file_controlled": False,
                              "source_result_ids": []},
        }),
        (b, "run-2"): _lineage_row(b, "run-2", **{
            "imported_from": {"source_run_id": "run-1", "source_result_id": a, "source_revision": 1,
                              "source_operation": "collection.search", "file_controlled": False,
                              "source_result_ids": []},
        }),
    }
    store = ToolResultStore()
    connection = FakeLineageConnection(sources)
    assert await store._is_file_controlled_snapshot(
        connection, row=dict(sources[(a, "run-1")]), tenant_id=uuid4(), user_id=uuid4(), visited=set(),
    ) is True

    orphan_id, known_id = str(uuid4()), str(uuid4())
    orphan_sources = {
        (known_id, "run-1"): _lineage_row(known_id, "run-1", source_result_ids=[orphan_id]),
    }
    assert await store._is_file_controlled_snapshot(
        FakeLineageConnection(orphan_sources), row=orphan_sources[(known_id, "run-1")],
        tenant_id=uuid4(), user_id=uuid4(), visited=set(),
    ) is True


@pytest.mark.asyncio
async def test_lineage_fails_closed_on_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [str(uuid4()) for _ in range(3)]
    sources: dict[tuple[str, str], dict | None] = {}
    for index, result_id in enumerate(ids):
        meta: dict[str, Any] = {}
        if index + 1 < len(ids):
            meta["imported_from"] = {
                "source_run_id": "run-1", "source_result_id": ids[index + 1],
                "source_revision": 1, "source_operation": "collection.search",
                "file_controlled": False, "source_result_ids": [],
            }
        sources[(result_id, "run-1")] = _lineage_row(result_id, "run-1", **meta)
    store = ToolResultStore()
    connection = FakeLineageConnection(sources)

    monkeypatch.setattr(get_settings(), "TOOL_RESULTS_LINEAGE_MAX_DEPTH", 1)
    assert await store._is_file_controlled_snapshot(
        connection, row=dict(sources[(ids[0], "run-1")]),
        tenant_id=uuid4(), user_id=uuid4(), visited=set(),
    ) is True

    chain: dict[tuple[str, str], dict | None] = {}
    chain_ids = [str(uuid4()) for _ in range(60)]
    for index, result_id in enumerate(chain_ids):
        meta = {}
        if index + 1 < len(chain_ids):
            meta["imported_from"] = {
                "source_run_id": "run-1", "source_result_id": chain_ids[index + 1],
                "source_revision": 1, "source_operation": "collection.search",
                "file_controlled": False, "source_result_ids": [],
            }
        chain[(result_id, "run-1")] = _lineage_row(result_id, "run-1", **meta)
    monkeypatch.setattr(get_settings(), "TOOL_RESULTS_LINEAGE_MAX_NODES", 51)
    assert await store._is_file_controlled_snapshot(
        FakeLineageConnection(chain), row=dict(chain[(chain_ids[0], "run-1")]),
        tenant_id=uuid4(), user_id=uuid4(), visited=set(),
    ) is True


@pytest.mark.asyncio
async def test_lineage_rejects_malformed_metadata_and_forbidden_operations() -> None:
    store = ToolResultStore()
    connection = FakeLineageConnection({})
    tenant_id, user_id = uuid4(), uuid4()

    unsafe_rows = [
        # imported_from is not an object
        _lineage_row(str(uuid4()), "run-1", imported_from="not-a-dict"),
        # imported_from misses required provenance fields
        _lineage_row(str(uuid4()), "run-1", imported_from={"source_run_id": "run-2"}),
        # provenance does not confirm a non-file-controlled source
        _lineage_row(str(uuid4()), "run-1", imported_from={
            "source_run_id": "run-2", "source_result_id": str(uuid4()), "source_revision": 1,
            "source_operation": "op", "file_controlled": True,
        }),
        # source_result_ids is not a list of UUIDs
        _lineage_row(str(uuid4()), "run-1", source_result_ids="not-a-list"),
        # forbidden operation spellings, including instance/underscore aliases
        _lineage_row(str(uuid4()), "run-1"),
        _lineage_row(str(uuid4()), "run-1"),
        _lineage_row(str(uuid4()), "run-1"),
    ]
    unsafe_rows[4]["operation"] = "instance.file.read"
    unsafe_rows[5]["operation"] = "memory_search"
    unsafe_rows[6]["operation"] = "collection.document.get"
    for row in unsafe_rows:
        assert await store._is_file_controlled_snapshot(
            connection, row=dict(row), tenant_id=tenant_id, user_id=user_id, visited=set(),
        ) is True

    safe_rows = [
        _lineage_row(str(uuid4()), "run-1"),
        _lineage_row(str(uuid4()), "run-1"),
    ]
    safe_rows[0]["operation"] = "collection.search"
    safe_rows[1]["operation"] = "instance_collection_search"
    for row in safe_rows:
        assert await store._is_file_controlled_snapshot(
            connection, row=dict(row), tenant_id=tenant_id, user_id=user_id, visited=set(),
        ) is False


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------


class FakeAnalyzeConnection:
    def __init__(
        self,
        *,
        authorized: dict | None = None,
        overview_rows: list | None = None,
        select_total: int = 0,
        select_rows: list | None = None,
        source_complete: Any = True,
        aggregate_rows: list | None = None,
        aggregate_count: int = 0,
        text_item: dict | None = None,
    ) -> None:
        self.authorized = authorized
        self.overview_rows = overview_rows or []
        self.select_total = select_total
        self.select_rows = select_rows or []
        self.source_complete = source_complete
        self.aggregate_rows = aggregate_rows or []
        self.aggregate_count = aggregate_count
        self.text_item = text_item
        self.page_params: dict | None = None

    async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
        rendered = str(statement)
        if "jsonb_typeof(payload) AS payload_type, source_total" in rendered:
            return FakeMappingsResult(first=self.authorized)
        if "LATERAL jsonb_each" in rendered:
            return FakeMappingsResult(rows=self.overview_rows)
        if "count(*) AS total" in rendered:
            return FakeMappingsResult(scalar_one=self.select_total)
        if "e.ordinality AS ordinal" in rendered:
            self.page_params = dict(params)
            return FakeMappingsResult(rows=self.select_rows)
        if "GROUP BY group_value" in rendered:
            return FakeMappingsResult(rows=self.aggregate_rows)
        if "SELECT source_complete FROM runtime_tool_payloads" in rendered:
            return FakeMappingsResult(scalar_one=self.source_complete)
        if "length(payload #>>" in rendered:
            return FakeMappingsResult(first=self.text_item)
        if "count(*)" in rendered:
            return FakeMappingsResult(scalar_one=self.aggregate_count)
        return FakeMappingsResult()


@pytest.mark.asyncio
async def test_analyze_validates_mode_and_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    # These checks run before the store touches the engine.
    forbid_engine(monkeypatch)
    store = ToolResultStore()
    base = {"result_id": str(uuid4()), "run_id": "run-1", "tenant_id": uuid4(), "user_id": uuid4()}

    with pytest.raises(ToolResultStoreError, match="Unsupported analysis mode: 'chart'"):
        await store.analyze(mode="chart", **base)
    with pytest.raises(ToolResultStoreError, match="paths is required for project"):
        await store.analyze(mode="project", **base)
    with pytest.raises(ToolResultStoreError, match="text_path is required for text"):
        await store.analyze(mode="text", text_path="", **base)
    with pytest.raises(ToolResultStoreError, match="result_id must be a UUID"):
        await store.analyze(result_id="nope", mode="overview", run_id="run-1",
                            tenant_id=uuid4(), user_id=uuid4())

    # The select/aggregate argument checks run after the result row is authorized.
    patch_engine(monkeypatch, FakeAnalyzeConnection(
        authorized={"payload_type": "array", "source_total": 1, "source_complete": True},
    ))
    select_base = {**base, "mode": "select", "array_path": "$"}
    with pytest.raises(ToolResultStoreError, match="array_path is required"):
        await store.analyze(mode="aggregate", **base)
    with pytest.raises(ToolResultStoreError, match="filter_path requires equals"):
        await store.analyze(filter_path="status", **select_base)
    with pytest.raises(ToolResultStoreError, match="filter_path is required when equals is provided"):
        await store.analyze(equals="open", **select_base)
    with pytest.raises(ToolResultStoreError, match="equals must be a string, number, boolean, or null"):
        await store.analyze(filter_path="status", equals=["open"], **select_base)
    with pytest.raises(ToolResultStoreError, match="equals must be a finite number"):
        await store.analyze(filter_path="status", equals=float("inf"), **select_base)


@pytest.mark.asyncio
async def test_analyze_overview_projects_bounded_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(
        authorized={"payload_type": "object", "source_total": 5, "source_complete": True},
        overview_rows=[
            {"key": "issues", "value_type": "array", "item_count": 2},
            {"key": "total", "value_type": "number", "item_count": None},
        ],
    )
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().analyze(
        result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(), mode="overview",
    )

    assert result["payload_type"] == "object"
    assert result["source_total"] == 5
    assert result["field_count"] == 2
    assert result["fields_complete"] is True
    assert result["fields"][0] == {"path": "issues", "type": "array", "item_count": 2}

    bounded = await ToolResultStore().analyze(
        result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
        mode="overview", response_budget_bytes=1,
    )
    assert bounded["fields"] == []
    assert bounded["fields_complete"] is False


@pytest.mark.asyncio
async def test_analyze_rejects_missing_authorized_row(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(authorized=None)
    patch_engine(monkeypatch, connection)
    with pytest.raises(ToolResultStoreError, match="Result not found or no longer available"):
        await ToolResultStore().analyze(
            result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            mode="overview",
        )


@pytest.mark.asyncio
async def test_analyze_select_pages_rows_with_clamped_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(
        authorized={"payload_type": "array", "source_total": 3, "source_complete": True},
        select_total=1,
        select_rows=[{"value": {"key": "OPS-1", "extra": 1}, "ordinal": 1}],
    )
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().analyze(
        result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
        mode="select", array_path="$", fields=["key"], limit=1000, offset=-5,
    )

    assert result["matched_count"] == 1
    assert result["rows"] == [{"ordinal": 0, "value": {"key": "OPS-1"}}]
    assert connection.page_params["limit"] == 50
    assert connection.page_params["offset"] == 0
    assert result["complete"] is True
    assert result["next_offset"] is None
    assert result["source_complete"] is True


@pytest.mark.asyncio
async def test_analyze_select_rejects_row_exceeding_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(
        authorized={"payload_type": "array", "source_total": 1, "source_complete": True},
        select_total=1,
        select_rows=[{"value": {"key": "OPS-1"}, "ordinal": 1}],
    )
    patch_engine(monkeypatch, connection)
    with pytest.raises(ToolResultStoreError, match="Selected row exceeds the response limit"):
        await ToolResultStore().analyze(
            result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            mode="select", array_path="$", response_budget_bytes=2,
        )


@pytest.mark.asyncio
async def test_analyze_aggregate_groups_and_truncates_values(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(
        authorized={"payload_type": "array", "source_total": 9, "source_complete": False},
        aggregate_rows=[{"group_value": "x" * 300, "count": 2, "group_total": 1}],
        source_complete=False,
    )
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().analyze(
        result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
        mode="aggregate", array_path="$", group_by="status",
    )

    assert result["groups"] == [{"value": "x" * 256, "count": 2}]
    assert result["group_total"] == 1
    assert result["groups_complete"] is True
    assert result["source_complete"] is False

    bounded = await ToolResultStore().analyze(
        result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
        mode="aggregate", array_path="$", group_by="status", response_budget_bytes=1,
    )
    assert bounded["groups"] == []
    assert bounded["groups_complete"] is False


@pytest.mark.asyncio
async def test_analyze_aggregate_without_group_by_counts_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(
        authorized={"payload_type": "array", "source_total": 7, "source_complete": True},
        aggregate_count=7,
    )
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().analyze(
        result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
        mode="aggregate", array_path="results",
    )

    assert result["count"] == 7
    assert result["source_complete"] is True


@pytest.mark.asyncio
async def test_analyze_text_returns_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(
        authorized={"payload_type": "object", "source_total": 1, "source_complete": True},
        text_item={"value_type": "string", "text_length": 3, "chunk": "abc"},
    )
    patch_engine(monkeypatch, connection)

    result = await ToolResultStore().analyze(
        result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
        mode="text", text_path="body",
    )

    assert result["chunk"] == "abc"
    assert result["length"] == 3
    assert result["complete"] is True
    assert result["next_offset"] is None


@pytest.mark.asyncio
async def test_analyze_text_validates_type_and_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeAnalyzeConnection(
        authorized={"payload_type": "object", "source_total": 1, "source_complete": True},
        text_item={"value_type": "number", "text_length": 1, "chunk": "1"},
    )
    patch_engine(monkeypatch, connection)
    with pytest.raises(ToolResultStoreError, match="text_path must reference a string"):
        await ToolResultStore().analyze(
            result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            mode="text", text_path="count",
        )

    connection.text_item = {"value_type": "string", "text_length": 4, "chunk": "zzzz"}
    with pytest.raises(ToolResultStoreError, match="No text chunk fits the remaining context budget"):
        await ToolResultStore().analyze(
            result_id=str(uuid4()), run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            mode="text", text_path="body", response_budget_bytes=2,
        )


# ---------------------------------------------------------------------------
# execute_sql()
# ---------------------------------------------------------------------------


class GenericConnection:
    async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
        return FakeMappingsResult()


class FakeQueryResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def mappings(self) -> FakeQueryResult:
        return self

    def __aiter__(self) -> Any:
        async def rows() -> Any:
            for row in self._rows:
                yield row
        return rows()


class StreamManager:
    def __init__(self, result: FakeQueryResult) -> None:
        self._result = result

    async def __aenter__(self) -> FakeQueryResult:
        return self._result

    async def __aexit__(self, *args: object) -> None:
        return None


class StreamConnection:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    async def execute(self, statement: object, params: Any = None) -> FakeMappingsResult:
        return FakeMappingsResult()

    def stream(self, statement: object, params: Any = None) -> StreamManager:
        return StreamManager(FakeQueryResult(self._rows))


@pytest.mark.asyncio
async def test_execute_sql_rejects_non_select_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_engine(monkeypatch)
    store = ToolResultStore()
    for sql in ("DELETE FROM x", "  ", "UPDATE t SET a = 1"):
        with pytest.raises(ToolResultStoreError, match="sql must be a SELECT query or a WITH query"):
            await store.execute_sql(
                sql=sql, run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
                call_id="call-1", task_id=None, agent_execution_id=None,
            )


@pytest.mark.asyncio
async def test_execute_sql_rejects_data_modifying_cte_in_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ToolResultStore()
    monkeypatch.setattr(store, "list_for_run", AsyncMock(return_value=[]))
    patch_engine(monkeypatch, GenericConnection())

    with pytest.raises(ToolResultStoreError, match="SQL query failed: Only read-only SELECT queries are allowed"):
        await store.execute_sql(
            sql="WITH deleted AS (DELETE FROM x RETURNING 1) SELECT * FROM deleted",
            run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            call_id="call-1", task_id=None, agent_execution_id=None,
        )


@pytest.mark.asyncio
async def test_execute_sql_runs_wrapped_query_and_persists_output(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ToolResultStore()
    monkeypatch.setattr(store, "list_for_run", AsyncMock(return_value=[]))
    saved = {
        "result_id": "a81f0000-0000-4000-8000-000000000001",
        "sql_ref": sql_ref_for_result("a81f0000-0000-4000-8000-000000000001"),
        "row_count": 1, "observed_schema": {}, "sample": None, "schema_complete": True,
        "inline_complete": True,
    }
    save = AsyncMock(return_value=saved)
    monkeypatch.setattr(store, "save", save)
    patch_engine(monkeypatch, StreamConnection([{"one": 1}]))

    result = await store.execute_sql(
        sql="SELECT 1 AS one ;", run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
        call_id="call-9", task_id="task-1", agent_execution_id=None,
        query_parameters={"p": 1},
    )

    assert result["mode"] == "sql"
    assert result["rows"] == [{"one": 1}]
    assert result["query_result_stored"] is True
    assert result["query_complete"] is True
    assert result["source_count"] == 0
    assert result["source_complete"] is None
    assert save.await_args.kwargs["operation"] == "result.analyze.sql"
    assert save.await_args.kwargs["query_sql"] == "SELECT 1 AS one"
    assert save.await_args.kwargs["arguments"] == {"query_parameters": {"p": 1}}


@pytest.mark.asyncio
async def test_execute_sql_enforces_expected_revisions(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ToolResultStore()
    result_id = str(uuid4())
    monkeypatch.setattr(store, "list_for_run", AsyncMock(return_value=[{
        "result_id": result_id, "sql_ref": sql_ref_for_result(result_id),
        "source_complete": True, "revision": 2,
    }]))
    patch_engine(monkeypatch, GenericConnection())

    with pytest.raises(ToolResultStoreError, match="Dataset revision changed"):
        await store.execute_sql(
            sql="SELECT 1", run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            call_id="call-1", task_id=None, agent_execution_id=None,
            expected_revisions={result_id: 1},
        )


@pytest.mark.asyncio
async def test_execute_sql_rejects_results_over_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "TOOL_RESULTS_SQL_MAX_ROWS", 1)
    store = ToolResultStore()
    monkeypatch.setattr(store, "list_for_run", AsyncMock(return_value=[]))
    save = AsyncMock()
    monkeypatch.setattr(store, "save", save)
    patch_engine(monkeypatch, StreamConnection([{"x": 1}, {"x": 2}]))

    with pytest.raises(ToolResultStoreError, match="SQL result exceeds the configured result limit"):
        await store.execute_sql(
            sql="SELECT 1 AS x", run_id="run-1", tenant_id=uuid4(),
            user_id=uuid4(), call_id="call-1", task_id=None, agent_execution_id=None,
        )
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_sql_wraps_unexpected_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class ExplodingStreamConnection(GenericConnection):
        def stream(self, statement: object, params: Any = None) -> StreamManager:
            raise RuntimeError("boom\nhidden detail")

    store = ToolResultStore()
    monkeypatch.setattr(store, "list_for_run", AsyncMock(return_value=[]))
    patch_engine(monkeypatch, ExplodingStreamConnection())

    with pytest.raises(ToolResultStoreError, match="SQL query failed: boom"):
        await store.execute_sql(
            sql="SELECT 1", run_id="run-1", tenant_id=uuid4(), user_id=uuid4(),
            call_id="call-1", task_id=None, agent_execution_id=None,
        )


# ---------------------------------------------------------------------------
# engine lifecycle and module helpers
# ---------------------------------------------------------------------------


def test_create_tool_results_engine_uses_configured_url(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    captured: dict[str, Any] = {}

    def fake_create_async_engine(url: str, **kwargs: Any) -> object:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(store_module, "create_async_engine", fake_create_async_engine)

    assert create_tool_results_engine() is sentinel
    assert captured["url"] == get_settings().TOOL_RESULTS_DB_URL
    assert captured["kwargs"]["pool_pre_ping"] is True
    assert captured["kwargs"]["json_deserializer"]('{"a": 1.5}') == {"a": Decimal("1.5")}


@pytest.mark.asyncio
async def test_engine_singleton_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(store_module, "_engine", sentinel)
    assert get_tool_results_engine() is sentinel

    created = object()
    monkeypatch.setattr(store_module, "create_tool_results_engine", lambda: created)
    monkeypatch.setattr(store_module, "_engine", None)
    assert get_tool_results_engine() is created
    assert store_module._engine is created

    engine = AsyncMock()
    monkeypatch.setattr(store_module, "_engine", engine)
    await dispose_tool_results_engine()
    engine.dispose.assert_awaited_once()
    assert store_module._engine is None
    await dispose_tool_results_engine()  # disposing again is a no-op


def test_json_exact_serialization_and_value_equality() -> None:
    assert _json_dumps_exact({"a": Decimal("1.500"), "b": [Decimal("2")]}) == '{"a": 1.500, "b": [2]}'
    with pytest.raises(ValueError, match="Non-finite Decimal"):
        _json_dumps_exact(Decimal("Infinity"))
    with pytest.raises(ValueError, match="Non-finite Decimal"):
        _json_dumps_exact(Decimal("NaN"))

    assert _json_values_equal(1, 1.0) is True
    assert _json_values_equal(True, 1) is False
    assert _json_values_equal([1, "a"], [1.0, "a"]) is True
    assert _json_values_equal({"a": 1}, {"a": 2}) is False
    assert _json_values_equal("1", 1) is False


def test_path_segments_parses_and_validates() -> None:
    assert _path_segments("a.b") == ["a", "b"]
    assert _path_segments("/rows/0/.name") == ["rows", "0", "name"]
    with pytest.raises(ToolResultStoreError, match="Invalid JSON path"):
        _path_segments("")
    with pytest.raises(ToolResultStoreError, match="Invalid JSON path"):
        _path_segments(".".join(f"f{i}" for i in range(13)))
    with pytest.raises(ToolResultStoreError, match="Invalid JSON path"):
        _path_segments("a." + "x" * 129)


def test_sql_ref_requires_a_uuid() -> None:
    with pytest.raises(ToolResultStoreError, match="Invalid saved result identifier"):
        sql_ref_for_result("not-a-uuid")


def test_response_value_budget_defaults_and_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _response_value_budget(0) == 1
    assert _response_value_budget(500) == 500
    assert _response_value_budget(None) == 2000
    monkeypatch.setattr(get_settings(), "TOOL_RESULTS_QUERY_CONTEXT_CHARS", 500)
    assert _response_value_budget(None) == 256


def test_source_total_and_completeness_combination() -> None:
    assert _source_total({"total": 5}) == 5
    assert _source_total({"count": 2}) == 2
    assert _source_total({"total": "5"}) is None
    assert _source_total({"total": True}) is None
    assert _source_total({"rows": []}) is None

    assert _combine_completeness([]) is None
    assert _combine_completeness([True, None]) is None
    assert _combine_completeness([True, False]) is False
    assert _combine_completeness([True, True]) is True
