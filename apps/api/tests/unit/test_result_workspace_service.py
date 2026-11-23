"""Unit tests for app.services.result_workspace (run-scoped dataset workspace)."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.services.result_workspace import (
    ResultWorkspace,
    SourceResultProtocolError,
    _bounded_model_meta,
    _describe_children,
    _json_kind,
    _json_pointer,
    normalized_page,
    page_key,
)
from app.services.tool_result_protocol import ResultPage
from app.services.tool_result_store import ToolResultStoreError

RUN_ID = "run-1"
CALL_ID = "call-1"
TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
RESULT_ID = "33333333-3333-3333-3333-333333333333"
SCOPE = {"result_id": RESULT_ID, "run_id": RUN_ID, "tenant_id": TENANT_ID, "user_id": USER_ID}


def read_settings(**overrides: Any) -> SimpleNamespace:
    values = {
        "TOOL_RESULTS_MAX_PAYLOAD_BYTES": 1_000_000,
        "TOOL_RESULTS_READ_MAX_ROWS": 200,
        "TOOL_RESULTS_CONTEXT_TOKENS": 500,
        "TOOL_RESULTS_QUERY_CONTEXT_CHARS": 50_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResult:
    def __init__(self, value: Any, mode: str) -> None:
        self._value = value
        self._mode = mode

    def mappings(self) -> "FakeResult":
        return self

    def first(self) -> Any:
        return self._value

    def all(self) -> Any:
        return self._value or []

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar(self) -> Any:
        return self._value


class FakeConnection:
    """Dispatch statements to the first handler whose marker matches."""

    def __init__(self, handlers: list[tuple[str, Any]]) -> None:
        self._handlers = handlers
        self.calls: list[tuple[str, Any]] = []

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False

    async def execute(self, stmt: Any, params: Any = None) -> FakeResult:
        sql = " ".join(str(stmt).split())
        self.calls.append((sql, params))
        for marker, handler in self._handlers:
            if marker in sql:
                outcome = handler(sql, params)
                if isinstance(outcome, Exception):
                    raise outcome
                if outcome is None:
                    return FakeResult(None, "none")
                mode, value = outcome
                return FakeResult(value, mode)
        raise AssertionError(f"unexpected statement: {sql}")


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def connect(self) -> FakeConnection:
        return self._connection

    def begin(self) -> FakeConnection:
        return self._connection


def make_state(**overrides: Any) -> dict[str, Any]:
    state = {
        "result_id": RESULT_ID,
        "call_id": CALL_ID,
        "operation": "collection.search",
        "arguments": {"offset": 0},
        "dataset_meta": {"source": "collection", "total": 2},
        "revision": 7,
        "row_count": 2,
        "source_total": 2,
        "source_complete": True,
        "observed_schema": {"a": {"types": ["number"], "path_segments": ["a"]}},
        "schema_complete": True,
        "sample": [],
        "sample_complete": True,
    }
    state.update(overrides)
    return state


class StubWorkspace(ResultWorkspace):
    """Workspace with a pinned state() so SQL-free methods stay unit-scoped."""

    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    async def state(self, **scope: Any) -> dict[str, Any]:
        return dict(self._state)


class TestBoundedModelMeta:
    def test_truncates_strings_lists_and_passes_through_scalars(self) -> None:
        meta = {
            "source": "s" * 400,
            "errors": ["e" * 200] * 25,
            "total": 5,
            "complete": True,
            "truncated": None,
        }
        bounded = _bounded_model_meta(meta)
        assert bounded["source"] == "s" * 300
        assert len(bounded["errors"]) == 20
        assert all(len(item) == 160 for item in bounded["errors"])
        assert bounded["total"] == 5
        assert bounded["complete"] is True
        assert bounded["truncated"] is None

    def test_input_revisions_keeps_integer_revisions_with_bounded_names(self) -> None:
        bounded = _bounded_model_meta(
            {"input_revisions": {"k" * 100: 3, "bad": "nope", "x": 7}}
        )
        assert bounded == {"input_revisions": {"k" * 64: 3, "x": 7}}

    def test_imported_from_is_projected_through_whitelist(self) -> None:
        bounded = _bounded_model_meta(
            {"imported_from": {"source_run_id": "r1", "extra": "drop", "source_revision": 2}}
        )
        assert bounded == {
            "imported_from": {"source_run_id": "r1", "source_revision": 2}
        }

    def test_unknown_keys_and_opaque_values_are_dropped(self) -> None:
        assert _bounded_model_meta({"weird": "x", "columns": {"a": 1}, "other": object()}) == {}


class TestPageKey:
    def test_is_canonical_sorted_sha256(self) -> None:
        expected = hashlib.sha256(
            json.dumps({"a": 2, "b": 1}, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        assert page_key({"b": 1, "a": 2}) == expected

    def test_distinguishes_different_arguments(self) -> None:
        assert page_key({"offset": 1}) != page_key({"offset": 2})


class TestJsonPointer:
    def test_empty_pointer_returns_whole_value(self) -> None:
        assert _json_pointer({"a": 1}, "") == {"a": 1}

    def test_requires_leading_slash(self) -> None:
        with pytest.raises(ToolResultStoreError, match="path must be an RFC 6901 JSON Pointer"):
            _json_pointer({"a": 1}, "a")

    def test_rejects_invalid_tilde_escape(self) -> None:
        with pytest.raises(ToolResultStoreError, match="path must be an RFC 6901 JSON Pointer"):
            _json_pointer({"a": 1}, "/a~2")

    def test_decodes_tilde_and_slash_escapes(self) -> None:
        assert _json_pointer({"a~b/c": 5}, "/a~0b~1c") == 5

    def test_traverses_dicts_and_arrays(self) -> None:
        assert _json_pointer([{"a": [10]}], "/0/a/0") == 10

    def test_rejects_leading_zero_index(self) -> None:
        with pytest.raises(ToolResultStoreError, match="JSON Pointer path not found"):
            _json_pointer([10], "/01")

    def test_rejects_out_of_range_index(self) -> None:
        with pytest.raises(ToolResultStoreError, match="JSON Pointer path not found: /5"):
            _json_pointer([1], "/5")

    def test_missing_key_names_the_pointer(self) -> None:
        with pytest.raises(ToolResultStoreError, match="JSON Pointer path not found: /b"):
            _json_pointer({"a": 1}, "/b")


class TestDescribeChildren:
    def test_dict_children_are_sorted_with_escaped_paths(self) -> None:
        value = {"b": 1, "a~x": {"z": 1}, "c": "s" * 200}
        paged = _describe_children(value, "/root", offset=0, limit=2)
        assert [child["key"] for child in paged["children"]] == ["a~x", "b"]
        assert paged["children"][0]["path"] == "/root/a~0x"
        assert paged["children"][0] == {"key": "a~x", "path": "/root/a~0x", "type": "object"}
        assert paged["children"][1]["value"] == 1
        assert paged["child_count"] == 3
        assert paged["next_child_offset"] == 2
        assert paged["children_complete"] is False

        full = _describe_children(value, "/root", offset=0, limit=3)
        assert full["children"][2] == {
            "key": "c",
            "path": "/root/c",
            "type": "string",
            "text_length": 200,
        }
        assert full["next_child_offset"] is None
        assert full["children_complete"] is True

    def test_list_children_use_indexes_and_offset_window(self) -> None:
        out = _describe_children(["x", {"a": 1}, [1, 2]], "", offset=1, limit=5)
        assert [child["index"] for child in out["children"]] == [1, 2]
        assert out["children"][0] == {"index": 1, "path": "/1", "type": "object"}
        assert out["children"][1] == {"index": 2, "path": "/2", "type": "array"}
        assert out["child_count"] == 3
        assert out["children_complete"] is True

    def test_short_strings_expose_value_and_scalars_return_value(self) -> None:
        out = _describe_children({"s": "ok"}, "/p", offset=0, limit=10)
        assert out["children"][0] == {"key": "s", "path": "/p/s", "type": "string", "value": "ok"}
        assert _describe_children(42, "/p", offset=0, limit=10) == {"value": 42}


class TestJsonKind:
    @pytest.mark.parametrize(
        ("value", "kind"),
        [
            ({}, "object"),
            ([], "array"),
            ("s", "string"),
            (None, "null"),
            (True, "boolean"),
            (False, "boolean"),
            (1, "number"),
            (1.5, "number"),
        ],
    )
    def test_maps_json_types(self, value: Any, kind: str) -> None:
        assert _json_kind(value) == kind

    def test_unknown_for_non_json_values(self) -> None:
        assert _json_kind(object()) == "unknown"


class TestNormalizedPage:
    def test_invalid_envelope_raises_protocol_error(self) -> None:
        with pytest.raises(SourceResultProtocolError, match="Source result protocol is invalid"):
            normalized_page({"value": [], "meta": {"has_next": True}}, "any_tool", {})

    def test_complete_conflict_raises_protocol_error(self) -> None:
        with pytest.raises(SourceResultProtocolError, match="Source result protocol is invalid"):
            normalized_page(
                {"value": [1], "meta": {"complete": True, "has_next": False, "total": 5}},
                "any_tool",
                {},
            )

    def test_valid_envelope_passes_through_with_extras(self) -> None:
        page = normalized_page(
            {"value": [1, 2], "meta": {"source": "x", "count": 2, "custom": "extra"}},
            "tool",
            {},
        )
        assert isinstance(page, ResultPage)
        assert page.value == [1, 2]
        assert page.meta.total == 2
        assert page.meta.model_dump()["custom"] == "extra"

    def test_generic_adapter_wraps_non_list_payload(self) -> None:
        page = normalized_page({"rows": [1]}, "unknown_tool", {"offset": 0})
        assert page.value == [{"rows": [1]}]
        assert page.meta.source == "unknown_tool"
        assert page.meta.complete is None


class TestSaveSource:
    @contextmanager
    def save_env(self, *, max_bytes: int = 1_000_000) -> Any:
        settings = SimpleNamespace(TOOL_RESULTS_MAX_PAYLOAD_BYTES=max_bytes)
        store_cls = MagicMock()
        store_cls.return_value.save = AsyncMock(return_value={"result_id": RESULT_ID})
        redactor_cls = MagicMock()
        redactor_cls.return_value.redact = MagicMock(side_effect=lambda value: value)
        with (
            patch("app.services.result_workspace.get_settings", return_value=settings),
            patch("app.services.result_workspace.ToolResultStore", store_cls),
            patch("app.runtime.redactor.RuntimeRedactor", redactor_cls),
        ):
            yield store_cls, redactor_cls

    async def test_persists_redacted_page_and_builds_model_view(self) -> None:
        payload = {
            "value": [{"k": 1}],
            "meta": {"source": "jira", "has_next": True, "next_arguments": {"start_at": 6}},
        }
        with self.save_env() as (store_cls, redactor_cls):
            descriptor, model_view = await ResultWorkspace().save_source(
                payload=payload,
                source_tool="execute_sql",
                arguments={"start_at": 3},
                run_id=RUN_ID,
                call_id=CALL_ID,
                operation="op",
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                task_id=None,
                agent_execution_id=None,
            )
        assert descriptor == {"result_id": RESULT_ID}
        redactor_cls.return_value.redact.assert_called_once_with([{"k": 1}])

        save_kwargs = store_cls.return_value.save.await_args.kwargs
        assert save_kwargs["payload"] == [{"k": 1}]
        assert save_kwargs["arguments"] == {"start_at": 3}
        assert save_kwargs["source_complete"] is None
        meta = save_kwargs["dataset_meta"]
        assert meta["source_tool"] == "execute_sql"
        assert meta["start_offset"] == 3
        assert meta["has_next"] is True
        assert meta["next_arguments"] == {"start_at": 6}
        source_page = save_kwargs["source_page"]
        assert source_page["page_key"] == page_key({"start_at": 3})
        assert source_page["value"] == [{"k": 1}]
        assert source_page["arguments"] == {"start_at": 3}

        assert model_view["value"] == [{"k": 1}]
        assert "next_arguments" not in model_view["meta"]
        assert model_view["meta"]["start_offset"] == 3
        assert model_view["meta"]["source_tool"] == "execute_sql"

    async def test_rejects_oversized_page_before_storing(self) -> None:
        with self.save_env(max_bytes=10) as (store_cls, _):
            with pytest.raises(
                ToolResultStoreError,
                match="Source page and metadata exceed the configured storage limit",
            ):
                await ResultWorkspace().save_source(
                    payload={"value": [], "meta": {}},
                    source_tool="execute_sql",
                    arguments={},
                    run_id=RUN_ID,
                    call_id=CALL_ID,
                    operation="op",
                    tenant_id=TENANT_ID,
                    user_id=USER_ID,
                    task_id=None,
                    agent_execution_id=None,
                )
        store_cls.return_value.save.assert_not_awaited()


class TestState:
    async def test_rejects_non_uuid_result_id(self) -> None:
        with pytest.raises(ToolResultStoreError, match="result_id must be a runtime-issued UUID"):
            await ResultWorkspace().state(
                result_id="not-a-uuid", run_id=RUN_ID, tenant_id=TENANT_ID, user_id=USER_ID
            )

    async def test_missing_row_reports_expired(self) -> None:
        connection = FakeConnection(
            [("FROM runtime_tool_payloads", lambda sql, params: ("first", None))]
        )
        engine = FakeEngine(connection)
        with patch("app.services.result_workspace.get_tool_results_engine", return_value=engine):
            with pytest.raises(
                ToolResultStoreError, match="Result not found or expired in this workspace"
            ):
                await ResultWorkspace().state(**SCOPE)

    async def test_returns_row_mapping(self) -> None:
        row = {"result_id": RESULT_ID, "revision": 4, "row_count": 1}
        connection = FakeConnection(
            [("FROM runtime_tool_payloads", lambda sql, params: ("first", row))]
        )
        engine = FakeEngine(connection)
        with patch("app.services.result_workspace.get_tool_results_engine", return_value=engine):
            state = await ResultWorkspace().state(**SCOPE)
        assert state == row
        sql, params = connection.calls[0]
        assert "expires_at>now()" in sql
        assert params == SCOPE


class TestDescribe:
    async def test_invalid_offset_or_limit(self) -> None:
        ws = StubWorkspace(make_state())
        for offset, limit in [(-1, 20), (0, 0), (0, 101)]:
            with pytest.raises(ToolResultStoreError, match="Invalid schema offset or limit"):
                await ws.describe(offset=offset, limit=limit, **SCOPE)

    async def test_projects_state_with_bounded_meta_and_schema_page(self) -> None:
        ws = StubWorkspace(make_state())
        schema_page = {
            "sql_columns": {"a": {"type": "numeric"}},
            "schema_total_columns": 1,
            "schema_page_complete": True,
        }
        with (
            patch("app.services.result_sql_projection.schema_page", return_value=schema_page) as sp,
            patch("app.services.tool_result_store.sql_ref_for_result", return_value="result_x") as ref,
            patch(
                "app.services.result_workspace.get_settings",
                return_value=read_settings(TOOL_RESULTS_CONTEXT_TOKENS=1000),
            ),
        ):
            out = await ws.describe(offset=1, limit=10, query="a", **SCOPE)
        assert out["sql_ref"] == "result_x"
        ref.assert_called_once_with(RESULT_ID)
        for removed in ("arguments", "observed_schema", "sample", "sample_complete"):
            assert removed not in out
        assert out["dataset_meta"] == _bounded_model_meta({"source": "collection", "total": 2})
        assert out["sql_columns"] == {"a": {"type": "numeric"}}
        assert out["schema_hint"].startswith("sql_columns are the exact")
        assert sp.call_args.kwargs == {
            "offset": 1,
            "limit": 10,
            "query": "a",
            "budget": sp.call_args.kwargs["budget"],
        }
        assert isinstance(sp.call_args.kwargs["budget"], int)
        assert sp.call_args.kwargs["budget"] >= 32

    async def test_context_budget_floor_is_32(self) -> None:
        ws = StubWorkspace(make_state())
        with (
            patch("app.services.result_sql_projection.schema_page", return_value={}) as sp,
            patch("app.services.tool_result_store.sql_ref_for_result", return_value="result_x"),
            patch(
                "app.services.result_workspace.get_settings",
                return_value=read_settings(TOOL_RESULTS_CONTEXT_TOKENS=1000),
            ),
        ):
            await ws.describe(context_budget_tokens=100, **SCOPE)
        assert sp.call_args.kwargs["budget"] == 32


class TestRead:
    async def test_revision_mismatch_requires_redescribe(self) -> None:
        ws = StubWorkspace(make_state(revision=7))
        with pytest.raises(
            ToolResultStoreError,
            match="Dataset revision changed; describe it and restart reading",
        ):
            await ws.read(revision=6, **SCOPE)

    async def test_invalid_offset_view_or_limits(self) -> None:
        ws = StubWorkspace(make_state())
        with patch(
            "app.services.result_workspace.get_settings", return_value=read_settings()
        ):
            for kwargs in [
                {"offset": -1},
                {"limit": 0},
                {"limit": 201},
                {"view": "bad"},
                {"child_limit": 0},
                {"child_limit": 201},
                {"text_offset": -1},
                {"child_offset": -1},
            ]:
                with pytest.raises(ToolResultStoreError, match="Invalid read offset or limit"):
                    await ws.read(**kwargs, **SCOPE)

    async def test_json_pointer_reads_require_limit_one(self) -> None:
        ws = StubWorkspace(make_state())
        with pytest.raises(
            ToolResultStoreError, match="JSON Pointer reads use limit=1"
        ):
            await ws.read(path="/a", limit=2, **SCOPE)

    async def test_json_pointer_text_limit_is_capped(self) -> None:
        ws = StubWorkspace(make_state())
        with pytest.raises(
            ToolResultStoreError, match="JSON Pointer text_limit cannot exceed 12000"
        ):
            await ws.read(path="/a", limit=1, text_limit=12001, **SCOPE)

    async def test_unknown_field_points_to_describe(self) -> None:
        ws = StubWorkspace(make_state())
        with patch(
            "app.services.result_sql_projection.sql_columns", return_value={}
        ):
            with pytest.raises(ToolResultStoreError, match="Unknown read field 'missing'"):
                await ws.read(fields=["missing"], **SCOPE)

    async def test_locked_revision_mismatch_requires_retry(self) -> None:
        ws = StubWorkspace(make_state(revision=7))
        connection = FakeConnection(
            [("FOR SHARE", lambda sql, params: ("scalar_one_or_none", 99))]
        )
        engine = FakeEngine(connection)
        with (
            patch("app.services.result_workspace.get_tool_results_engine", return_value=engine),
            patch("app.services.result_sql_projection.sql_columns", return_value={}),
            patch("app.services.result_workspace.get_settings", return_value=read_settings()),
        ):
            with pytest.raises(ToolResultStoreError, match="Dataset revision changed; retry the read"):
                await ws.read(**SCOPE)

    def read_engine(
        self, revision: int, records: list[dict[str, Any]]
    ) -> FakeEngine:
        def rows(sql: str, params: Any) -> tuple[str, Any]:
            offset, limit = params["offset"], params["limit"]
            return ("all", records[offset:offset + limit])

        connection = FakeConnection(
            [
                ("FOR SHARE", lambda sql, params: ("scalar_one_or_none", revision)),
                ("FROM runtime_tool_result_rows", rows),
            ]
        )
        return FakeEngine(connection)

    @contextmanager
    def read_patches(
        self,
        engine: FakeEngine,
        settings: SimpleNamespace | None = None,
        columns: dict[str, Any] | None = None,
    ) -> Any:
        with (
            patch("app.services.result_workspace.get_tool_results_engine", return_value=engine),
            patch(
                "app.services.result_sql_projection.sql_columns",
                return_value=columns if columns is not None else {
                    "a": {"path": ["a"], "type": "numeric"},
                },
            ),
            patch(
                "app.services.result_workspace.get_settings",
                return_value=settings or read_settings(),
            ),
        ):
            yield

    async def test_value_projection_and_pagination(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=3, source_complete=True))
        records = [{"ordinal": index, "data": {"a": index}} for index in range(3)]
        engine = self.read_engine(7, records)
        with self.read_patches(engine):
            out = await ws.read(offset=0, limit=2, **SCOPE)
        assert out["value"] == [{"a": 0}, {"a": 1}]
        assert out["returned_count"] == 2
        assert out["next_offset"] == 2
        assert out["read_complete"] is False
        assert out["view"] == "value"
        assert out["revision"] == 7
        assert out["loaded_items"] == 3
        assert out["source_complete"] is True
        assert out["record_too_large"] is False
        assert out["hint"] is None
        assert "requested_fields" not in out
        assert out["snapshot_only"] is False
        assert out["imported_from"] is None

    async def test_field_projection_uses_declared_columns(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=2))
        records = [
            {"ordinal": 0, "data": {"a": 1, "b": 10}},
            {"ordinal": 1, "data": {"a": 2, "b": 20}},
        ]
        engine = self.read_engine(7, records)
        with self.read_patches(
            engine,
            columns={
                "a": {"path": ["a"], "type": "numeric"},
                "b": {"path": ["b"], "type": "numeric"},
            },
        ):
            out = await ws.read(fields=["a", "b"], **SCOPE)
        assert out["value"] == [{"a": 1, "b": 10}, {"a": 2, "b": 20}]
        assert out["requested_fields"] == ["a", "b"]
        assert out["fields"] == ["a", "b"]

    async def test_empty_page_reports_complete_read(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=3))
        engine = self.read_engine(7, [])
        with self.read_patches(engine):
            out = await ws.read(offset=3, limit=5, **SCOPE)
        assert out["value"] == []
        assert out["next_offset"] is None
        assert out["read_complete"] is True
        assert out["record_too_large"] is False

    async def test_json_pointer_string_read_with_text_window(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1, dataset_meta={}))
        records = [{"ordinal": 0, "data": {"text": "0123456789"}}]
        engine = self.read_engine(7, records)
        with self.read_patches(engine):
            out = await ws.read(path="/text", limit=1, text_offset=2, text_limit=4, **SCOPE)
        assert out["value"] == ["2345"]
        assert out["applied_text_limit"] == 4
        assert out["next_text_offset"] == 6
        assert out["read_complete"] is False
        assert out["view"] == "auto"

    async def test_json_pointer_children_view(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1, dataset_meta={}))
        records = [{"ordinal": 0, "data": {"obj": {"k1": 1, "k2": 2}}}]
        engine = self.read_engine(7, records)
        with self.read_patches(engine):
            out = await ws.read(path="/obj", view="children", child_offset=1, limit=1, **SCOPE)
        assert out["view"] == "children"
        children_payload = out["value"][0]
        assert [child["key"] for child in children_payload["children"]] == ["k2"]
        assert children_payload["child_offset"] == 1
        assert children_payload["children_complete"] is True
        assert out["next_child_offset"] is None
        assert out["read_complete"] is True

    async def test_auto_view_keeps_compact_structures_inline(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1, dataset_meta={}))
        records = [{"ordinal": 0, "data": {"obj": {"k": 1}}}]
        engine = self.read_engine(7, records)
        with self.read_patches(engine):
            out = await ws.read(path="/obj", limit=1, **SCOPE)
        assert out["value"] == [{"k": 1}]
        assert out["view"] == "auto"
        assert out["next_child_offset"] is None

    async def test_unknown_pointer_path_propagates_store_error(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1))
        records = [{"ordinal": 0, "data": {"a": 1}}]
        engine = self.read_engine(7, records)
        with self.read_patches(engine):
            with pytest.raises(ToolResultStoreError, match="JSON Pointer path not found: /missing"):
                await ws.read(path="/missing", limit=1, **SCOPE)

    async def test_oversized_rows_report_record_too_large(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1))
        records = [{"ordinal": 0, "data": {"a": "x" * 100}}]
        engine = self.read_engine(7, records)
        settings = read_settings(TOOL_RESULTS_CONTEXT_TOKENS=344)
        with self.read_patches(engine, settings):
            out = await ws.read(limit=1, **SCOPE)
        assert out["value"] == []
        assert out["record_too_large"] is True
        assert out["hint"] == "Select fewer fields or use result.sql for oversized records."
        assert out["next_offset"] is None
        assert out["read_complete"] is False

    async def test_long_strings_shrink_by_halving_with_text_cursor(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1, dataset_meta={}))
        records = [{"ordinal": 0, "data": {"text": "x" * 800}}]
        engine = self.read_engine(7, records)
        with self.read_patches(engine):
            out = await ws.read(path="/text", limit=1, **SCOPE)
        value = out["value"][0]
        assert 0 < len(value) < 800
        assert out["applied_text_limit"] == len(value)
        assert out["next_text_offset"] == len(value)
        assert out["read_complete"] is False

    async def test_children_shrink_keeps_at_least_one_child(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1, dataset_meta={}))
        records = [{"ordinal": 0, "data": {"obj": {f"key{index}": index for index in range(20)}}}]
        engine = self.read_engine(7, records)
        with self.read_patches(engine):
            out = await ws.read(path="/obj", view="children", limit=1, **SCOPE)
        children = out["value"][0]["children"]
        assert 1 <= len(children) < 20
        assert out["value"][0]["children_complete"] is False
        assert out["value"][0]["next_child_offset"] == len(children)
        assert out["next_child_offset"] == len(children)
        assert out["read_complete"] is False

    async def test_context_token_budget_switches_to_children_view(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1, dataset_meta={}))
        records = [{"ordinal": 0, "data": {"obj": {f"key{index}": index for index in range(25)}}}]
        engine = self.read_engine(7, records)
        with (
            self.read_patches(engine),
            patch(
                "app.adapters.impl.llm_context.estimate_request_tokens",
                side_effect=[999, 1],
            ) as estimate,
        ):
            out = await ws.read(path="/obj", limit=1, child_limit=20, context_budget_tokens=10, **SCOPE)
        assert estimate.call_count == 2
        assert out["view"] == "children"
        children = out["value"][0]["children"]
        assert len(children) == 20
        assert out["next_child_offset"] == 20
        assert out["read_complete"] is False

    async def test_context_token_budget_halves_long_strings(self) -> None:
        ws = StubWorkspace(make_state(revision=7, row_count=1, dataset_meta={}))
        records = [{"ordinal": 0, "data": {"text": "x" * 800}}]
        engine = self.read_engine(7, records)
        with (
            self.read_patches(engine),
            patch(
                "app.adapters.impl.llm_context.estimate_request_tokens",
                side_effect=[999, 1],
            ),
        ):
            out = await ws.read(path="/text", limit=1, context_budget_tokens=10, **SCOPE)
        value = out["value"][0]
        assert 0 < len(value) < 800
        assert out["applied_text_limit"] == len(value)
        assert out["next_text_offset"] == len(value)
        assert out["read_complete"] is False


class TestStandardQuery:
    def query_env(self, revision: int = 7):
        ws = StubWorkspace(make_state(revision=revision))
        store_cls = MagicMock()
        store_cls.return_value.execute_sql = AsyncMock(
            return_value={"rows": [["x", 2]], "row_count": 1, "truncated": False}
        )
        return ws, store_cls

    @contextmanager
    def query_patches(self, store_cls: MagicMock, columns: dict[str, Any]) -> Any:
        with (
            patch("app.services.result_workspace.ToolResultStore", store_cls),
            patch("app.services.result_sql_projection.sql_columns", return_value=columns),
            patch(
                "app.services.tool_result_store.sql_ref_for_result", return_value="result_abc"
            ),
        ):
            yield

    async def test_revision_mismatch_requires_restart(self) -> None:
        ws, _ = self.query_env(revision=7)
        with pytest.raises(
            ToolResultStoreError,
            match="Dataset revision changed; restart pagination from result.describe",
        ):
            await ws.standard_query(
                kind="find", q="x", revision=6, call_id=CALL_ID, task_id=None,
                agent_execution_id=None, **SCOPE,
            )

    async def test_unknown_column(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {"a": {"path": ["a"], "type": "text"}}):
            with pytest.raises(ToolResultStoreError, match="Unknown column 'nope'; use result.describe"):
                await ws.standard_query(
                    kind="find", q="x", columns=["nope"], call_id=CALL_ID, task_id=None,
                    agent_execution_id=None, **SCOPE,
                )

    async def test_invalid_offset_or_limit(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {"a": {"path": ["a"], "type": "text"}}):
            for kwargs in [{"limit": 0}, {"limit": 101}, {"offset": -1}]:
                with pytest.raises(ToolResultStoreError, match="Invalid query offset or limit"):
                    await ws.standard_query(
                        kind="find", q="x", call_id=CALL_ID, task_id=None,
                        agent_execution_id=None, **kwargs, **SCOPE,
                    )

    async def test_aggregate_requires_distinct_columns(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {"a": {"path": ["a"], "type": "text"}}):
            for columns in [None, ["a", "a"]]:
                with pytest.raises(
                    ToolResultStoreError, match="aggregate requires distinct grouping columns"
                ):
                    await ws.standard_query(
                        kind="aggregate", columns=columns, call_id=CALL_ID, task_id=None,
                        agent_execution_id=None, **SCOPE,
                    )

    async def test_find_requires_nonempty_query(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {}):
            with pytest.raises(ToolResultStoreError, match="find requires a nonempty q"):
                await ws.standard_query(
                    kind="find", q="   ", call_id=CALL_ID, task_id=None,
                    agent_execution_id=None, **SCOPE,
                )

    async def test_unknown_kind(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {}):
            with pytest.raises(ToolResultStoreError, match="Unknown standard query"):
                await ws.standard_query(
                    kind="describe", call_id=CALL_ID, task_id=None,
                    agent_execution_id=None, **SCOPE,
                )

    async def test_aggregate_builds_quoted_grouping_sql(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {"a": {"path": ["a"], "type": "text"}}):
            out = await ws.standard_query(
                kind="aggregate", columns=["a"], offset=0, limit=20,
                call_id=CALL_ID, task_id="t1", agent_execution_id="e1", **SCOPE,
            )
        kwargs = store_cls.return_value.execute_sql.await_args.kwargs
        assert kwargs["sql"] == (
            'SELECT "a", count(*) AS "count" FROM result_abc '
            'GROUP BY "a" ORDER BY "count" DESC, "a" LIMIT 20 OFFSET 0'
        )
        assert kwargs["query_parameters"] == {}
        assert kwargs["expected_revisions"] == {RESULT_ID: 7}
        assert kwargs["call_id"] == CALL_ID
        assert kwargs["task_id"] == "t1"
        assert kwargs["agent_execution_id"] == "e1"
        assert kwargs["run_id"] == RUN_ID
        assert "result_id" not in kwargs
        assert out["operation"] == "aggregate"
        assert out["input_result_id"] == RESULT_ID
        assert out["input_revision"] == 7
        assert out["offset"] == 0
        assert out["limit"] == 20
        assert out["page_may_have_more"] is False
        assert out["query_complete"] is True
        assert out["columns"] == ["a"]
        assert "q" not in out

    async def test_aggregate_count_column_collision_is_prefixed(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {"count": {"path": ["count"], "type": "text"}}):
            await ws.standard_query(
                kind="aggregate", columns=["count"], call_id=CALL_ID, task_id=None,
                agent_execution_id=None, **SCOPE,
            )
        sql = store_cls.return_value.execute_sql.await_args.kwargs["sql"]
        assert sql.startswith('SELECT "count", count(*) AS "_count" FROM result_abc')
        assert 'ORDER BY "_count" DESC' in sql

    async def test_find_escapes_query_and_enriches_output(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {"a": {"path": ["a"], "type": "text"}}):
            out = await ws.standard_query(
                kind="find", q='a"b', offset=5, limit=10,
                call_id=CALL_ID, task_id=None, agent_execution_id=None, **SCOPE,
            )
        kwargs = store_cls.return_value.execute_sql.await_args.kwargs
        assert kwargs["query_parameters"] == {"workspace_find_q": json.dumps('a"b', ensure_ascii=False)[1:-1]}
        assert kwargs["sql"] == (
            "SELECT * FROM result_abc AS _records "
            "WHERE strpos(lower(to_jsonb(_records)::text), lower(:workspace_find_q)) > 0 "
            "ORDER BY to_jsonb(_records)::text LIMIT 10 OFFSET 5"
        )
        assert out["operation"] == "find"
        assert out["q"] == 'a"b'
        assert "columns" not in out

    async def test_find_with_columns_selects_them_quoted(self) -> None:
        ws, store_cls = self.query_env()
        with self.query_patches(store_cls, {"a": {"path": ["a"], "type": "text"}}):
            await ws.standard_query(
                kind="find", q="x", columns=["a"], call_id=CALL_ID, task_id=None,
                agent_execution_id=None, **SCOPE,
            )
        sql = store_cls.return_value.execute_sql.await_args.kwargs["sql"]
        assert sql.startswith('SELECT "a" FROM result_abc')

    async def test_truncated_page_reports_incomplete_query(self) -> None:
        ws, store_cls = self.query_env()
        store_cls.return_value.execute_sql = AsyncMock(
            return_value={"rows": [], "row_count": 20, "truncated": True}
        )
        with self.query_patches(store_cls, {"a": {"path": ["a"], "type": "text"}}):
            out = await ws.standard_query(
                kind="aggregate", columns=["a"], limit=20, call_id=CALL_ID, task_id=None,
                agent_execution_id=None, **SCOPE,
            )
        assert out["page_may_have_more"] is True
        assert out["query_complete"] is False


class AppendHarness:
    """Engine double capturing every append_page statement."""

    def __init__(self, row: dict[str, Any] | None, *, exists: Any = None, cycle: bool = False) -> None:
        self.row = row
        self.exists = exists
        self.cycle = cycle
        self.pages: list[Any] = []
        self.row_batches: list[Any] = []
        self.payload_updates: list[Any] = []
        self.meta_updates: list[Any] = []
        self.inspect = AsyncMock(return_value={"col": {"type": "text"}})
        self.connection = FakeConnection(
            [
                ("FOR UPDATE", lambda sql, params: ("first", self.row)),
                ("page_key=:key", lambda sql, params: ("scalar_one_or_none", self.exists)),
                ("page_key=:next_key", lambda sql, params: ("scalar", 1 if self.cycle else None)),
                ("INSERT INTO runtime_tool_result_pages", self._record(self.pages)),
                ("INSERT INTO runtime_tool_result_rows", self._record(self.row_batches)),
                ("UPDATE runtime_tool_payloads SET payload=", self._record(self.payload_updates)),
                ("UPDATE runtime_tool_payloads SET dataset_meta=", self._record(self.meta_updates)),
            ]
        )
        self.engine = FakeEngine(self.connection)

    @staticmethod
    def _record(sink: list[Any]):
        def handler(sql: str, params: Any) -> None:
            sink.append(params)

        return handler


class TestAppendPage:
    @contextmanager
    def append_env(self, harness: AppendHarness, *, max_bytes: int = 1_000_000) -> Any:
        settings = SimpleNamespace(TOOL_RESULTS_MAX_PAYLOAD_BYTES=max_bytes)
        redactor_cls = MagicMock()
        redactor_cls.return_value.redact = MagicMock(side_effect=lambda value: value)
        with (
            patch(
                "app.services.result_workspace.get_tool_results_engine",
                return_value=harness.engine,
            ),
            patch("app.services.result_workspace.get_settings", return_value=settings),
            patch(
                "app.services.result_workspace._profile_rows",
                return_value=({}, [], True, True),
            ),
            patch("app.runtime.redactor.RuntimeRedactor", redactor_cls),
            patch("app.services.result_sql_projection.sql_columns", return_value={}),
            patch(
                "app.services.result_sql_projection.inspect_table", harness.inspect
            ),
        ):
            yield

    def base_row(self, **meta_overrides: Any) -> dict[str, Any]:
        meta = {
            "source": "sql",
            "total": 4,
            "start_offset": 0,
            "complete": False,
            "has_next": True,
            "next_arguments": {"offset": 1},
        }
        meta.update(meta_overrides)
        return {"payload": [{"a": 1}], "row_count": 1, "revision": 5, "dataset_meta": meta}

    async def test_happy_path_persists_page_rows_and_metadata(self) -> None:
        harness = AppendHarness(self.base_row())
        payload = {"value": [{"a": 2}, {"a": 3}], "meta": {"source": "sql", "total": 4, "has_next": False}}
        with self.append_env(harness):
            out = await ResultWorkspace().append_page(
                payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                expected_revision=5, call_id=CALL_ID, **SCOPE,
            )
        assert out == {"appended": True, "revision": 6}
        assert len(harness.pages) == 1
        assert harness.pages[0]["key"] == page_key({"offset": 1})
        assert harness.pages[0]["call_id"] == CALL_ID
        assert len(harness.row_batches) == 1
        appended_rows = [
            (item["ordinal"], json.loads(item["data"])) for item in harness.row_batches[0]
        ]
        assert appended_rows == [(1, {"a": 2}), (2, {"a": 3})]
        assert len(harness.payload_updates) == 1
        assert len(harness.meta_updates) == 1
        meta = json.loads(harness.meta_updates[0]["meta"])
        assert meta["complete"] is False
        assert meta["total"] == 4
        assert meta["has_next"] is False
        assert meta["table_schema"] == {"col": {"type": "text"}}
        harness.inspect.assert_awaited_once()
        assert harness.inspect.await_args.args[0] is harness.connection
        assert harness.inspect.await_args.kwargs["result_id"] == RESULT_ID
        update_payload = harness.payload_updates[0]
        assert update_payload["count"] == 3
        assert update_payload["complete"] is False
        assert update_payload["total"] == 4

    async def test_existing_page_key_is_idempotent(self) -> None:
        harness = AppendHarness(self.base_row(), exists=1)
        payload = {"value": [{"a": 2}], "meta": {"source": "sql", "total": 4, "has_next": False}}
        with self.append_env(harness):
            out = await ResultWorkspace().append_page(
                payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                expected_revision=5, call_id=CALL_ID, **SCOPE,
            )
        assert out == {"appended": False, "revision": 5}
        assert harness.pages == []
        assert harness.row_batches == []
        assert harness.payload_updates == []
        assert harness.meta_updates == []

    async def test_missing_row_reports_expired(self) -> None:
        harness = AppendHarness(None)
        payload = {"value": [{"a": 2}], "meta": {"source": "sql", "total": 4, "has_next": False}}
        with self.append_env(harness):
            with pytest.raises(ToolResultStoreError, match="Result not found or expired"):
                await ResultWorkspace().append_page(
                    payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                    expected_revision=5, call_id=CALL_ID, **SCOPE,
                )

    async def test_revision_conflict_requires_retry(self) -> None:
        harness = AppendHarness(self.base_row().copy())
        harness.row["revision"] = 6
        payload = {"value": [{"a": 2}], "meta": {"source": "sql", "total": 4, "has_next": False}}
        with self.append_env(harness):
            with pytest.raises(
                ToolResultStoreError, match="Dataset changed while fetching; retry continuation"
            ):
                await ResultWorkspace().append_page(
                    payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                    expected_revision=5, call_id=CALL_ID, **SCOPE,
                )

    async def test_page_must_match_saved_continuation(self) -> None:
        harness = AppendHarness(self.base_row(next_arguments={"offset": 9}))
        payload = {"value": [{"a": 2}], "meta": {"source": "sql", "total": 4, "has_next": False}}
        with self.append_env(harness):
            with pytest.raises(ToolResultStoreError, match="Page does not match the saved continuation"):
                await ResultWorkspace().append_page(
                    payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                    expected_revision=5, call_id=CALL_ID, **SCOPE,
                )

    async def test_storage_budget_keeps_saved_pages(self) -> None:
        harness = AppendHarness(self.base_row())
        payload = {"value": [{"a": 2}], "meta": {"source": "sql", "total": 4, "has_next": False}}
        with self.append_env(harness, max_bytes=10):
            with pytest.raises(
                ToolResultStoreError, match="Dataset storage budget reached; saved pages remain available"
            ):
                await ResultWorkspace().append_page(
                    payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                    expected_revision=5, call_id=CALL_ID, **SCOPE,
                )
        assert harness.pages == []
        assert harness.payload_updates == []

    async def test_oversized_raw_page_is_rejected(self) -> None:
        harness = AppendHarness(self.base_row())
        harness.row["payload"] = []
        harness.row["row_count"] = 0
        payload = {"value": [{"a": 1}], "meta": {"extra": "x" * 300}}
        with self.append_env(harness, max_bytes=100):
            with pytest.raises(
                ToolResultStoreError,
                match="Source page and metadata exceed the configured storage limit",
            ):
                await ResultWorkspace().append_page(
                    payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                    expected_revision=5, call_id=CALL_ID, **SCOPE,
                )

    async def test_source_continuation_must_advance(self) -> None:
        harness = AppendHarness(self.base_row())
        payload = {"value": [{"a": 2}], "meta": {"has_next": True, "next_arguments": {"offset": 1}}}
        with self.append_env(harness):
            with pytest.raises(ToolResultStoreError, match="Source continuation did not advance"):
                await ResultWorkspace().append_page(
                    payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                    expected_revision=5, call_id=CALL_ID, **SCOPE,
                )
        assert harness.pages == []
        assert harness.payload_updates == []

    async def test_continuation_cycle_is_recorded_not_looping(self) -> None:
        harness = AppendHarness(self.base_row(), cycle=True)
        payload = {
            "value": [{"a": 2}],
            "meta": {"has_next": True, "next_arguments": {"offset": 2}},
        }
        with self.append_env(harness):
            out = await ResultWorkspace().append_page(
                payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                expected_revision=5, call_id=CALL_ID, **SCOPE,
            )
        assert out == {"appended": True, "revision": 6}
        assert len(harness.meta_updates) == 1
        meta = json.loads(harness.meta_updates[0]["meta"])
        assert meta["has_next"] is True
        assert meta["next_arguments"] is None
        assert meta["coverage_incomplete"] is True
        assert meta["continuation_error"] == "Source continuation cycles to an already loaded page"

    async def test_collection_source_takes_coverage_from_new_page_only(self) -> None:
        harness = AppendHarness(
            self.base_row(
                source="collection",
                coverage_incomplete=True,
                total=2,
            )
        )
        payload = {"value": [{"a": 2}], "meta": {"source": "collection", "has_next": False, "total": None}}
        with self.append_env(harness):
            out = await ResultWorkspace().append_page(
                payload=payload, source_tool="collection_search", arguments={"offset": 1},
                expected_revision=5, call_id=CALL_ID, **SCOPE,
            )
        assert out == {"appended": True, "revision": 6}
        meta = json.loads(harness.meta_updates[0]["meta"])
        assert meta["coverage_incomplete"] is False
        assert meta["complete"] is True

    async def test_complete_stays_unknown_without_page_coverage_signal(self) -> None:
        harness = AppendHarness(self.base_row())
        payload = {"value": [{"a": 2}], "meta": {"source": "sql", "total": 4}}
        with self.append_env(harness):
            out = await ResultWorkspace().append_page(
                payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                expected_revision=5, call_id=CALL_ID, **SCOPE,
            )
        assert out == {"appended": True, "revision": 6}
        meta = json.loads(harness.meta_updates[0]["meta"])
        assert meta["complete"] is None

    async def test_complete_stays_unknown_when_saved_state_is_unknown(self) -> None:
        harness = AppendHarness(self.base_row(complete=None))
        payload = {"value": [{"a": 2}], "meta": {"source": "sql", "total": 4, "has_next": False}}
        with self.append_env(harness):
            await ResultWorkspace().append_page(
                payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                expected_revision=5, call_id=CALL_ID, **SCOPE,
            )
        meta = json.loads(harness.meta_updates[0]["meta"])
        assert meta["complete"] is None

    async def test_row_batches_chunked_by_thousand(self) -> None:
        harness = AppendHarness(self.base_row())
        harness.row["payload"] = []
        harness.row["row_count"] = 0
        values = [{"i": index} for index in range(2500)]
        payload = {"value": values, "meta": {"source": "sql", "total": 2500, "has_next": False}}
        with self.append_env(harness, max_bytes=10_000_000):
            out = await ResultWorkspace().append_page(
                payload=payload, source_tool="execute_sql", arguments={"offset": 1},
                expected_revision=5, call_id=CALL_ID, **SCOPE,
            )
        assert out == {"appended": True, "revision": 6}
        assert [len(batch) for batch in harness.row_batches] == [1000, 1000, 500]
        flat_ordinals = [item["ordinal"] for batch in harness.row_batches for item in batch]
        assert flat_ordinals == list(range(2500))
        assert harness.payload_updates[0]["count"] == 2500
