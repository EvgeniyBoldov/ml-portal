"""Unit tests for CollectionAggregateTool (collection.aggregate flow and helpers)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.collection_aggregate import CollectionAggregateTool
from app.agents.context import ToolContext
from app.models.collection import Collection, CollectionType, FieldCategory, FieldType
from app.services.collection_service import CollectionService


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
        "fields": [
            {
                "name": "title",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.TEXT.value,
                "required": True,
                "description": "Title",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
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
                "name": "opened_at",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.DATETIME.value,
                "required": False,
                "description": "Opened at",
                "filterable": True,
                "sortable": True,
                "used_in_retrieval": False,
                "used_in_prompt_context": True,
            },
            {
                "name": "meta",
                "category": FieldCategory.USER.value,
                "data_type": FieldType.JSON.value,
                "required": False,
                "description": "Meta",
                "filterable": False,
                "sortable": False,
                "used_in_retrieval": False,
                "used_in_prompt_context": False,
            },
            {
                "name": "code",
                "category": FieldCategory.SPECIFIC.value,
                "data_type": FieldType.STRING.value,
                "required": False,
                "description": "Type-owned code",
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


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)

    def scalar(self):
        return self._scalar


class _FakeSession:
    """Executes SET LOCAL + one aggregate SELECT; records executed statements."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed: list[tuple[str, dict | None]] = []

    async def execute(self, clause, params=None):
        sql = str(clause)
        self.executed.append((sql, params))
        if sql.startswith("SET LOCAL"):
            return _FakeResult(rows=[])
        return _FakeResult(rows=self._rows)


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _install(monkeypatch, session, collection):
    monkeypatch.setattr(
        "app.core.db.get_session_factory", lambda: lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        CollectionService, "get_by_slug", AsyncMock(return_value=collection)
    )


async def _run(monkeypatch, args, collection=None, rows=None):
    collection = collection if collection is not None else _collection()
    session = _FakeSession(rows=rows)
    _install(monkeypatch, session, collection)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    return await CollectionAggregateTool().v1_0_0(ctx, args), session


def _norm(sql: str) -> str:
    return " ".join(sql.split())


# ─────────────────────────────────────────────────────────────────────────────
# Flow: happy path
# ─────────────────────────────────────────────────────────────────────────────


async def test_happy_path_group_by_time_bucket_having_order(monkeypatch):
    rows = [
        {"priority": 1, "time_bucket": "2026-01-02", "metric_0": 7, "avg_priority": 2.5},
        {"priority": 2, "time_bucket": "2026-01-03", "metric_0": 9, "avg_priority": 3.0},
    ]
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [
                {"function": "count"},
                {"function": "avg", "field": "priority", "alias": "avg_priority"},
            ],
            "group_by": ["priority"],
            "filters": {"and": [{"field": "opened_at", "op": "gte", "value": "2026-01-01"}]},
            "time_bucket": {"field": "opened_at", "interval": "day"},
            "having": [{"function": "count", "op": "gt", "value": 5}],
            "order_by": "-avg_priority",
        },
        rows=rows,
    )

    assert result.success is True
    assert result.data["results"] == rows
    assert result.data["total_groups"] == 2
    assert result.data["collection"] == "tickets"

    assert len(session.executed) == 2
    timeout_sql, _ = session.executed[0]
    assert timeout_sql == "SET LOCAL statement_timeout = '10s'"

    agg_sql, agg_params = session.executed[1]
    assert _norm(agg_sql) == (
        "SELECT priority, date_trunc('day', opened_at) as time_bucket, "
        "COUNT(*) as metric_0, AVG(priority) as avg_priority "
        "FROM coll_test_tickets "
        "WHERE opened_at >= :p0 "
        "GROUP BY priority, date_trunc('day', opened_at) "
        "HAVING COUNT(*) > :h1 "
        "ORDER BY avg_priority DESC "
        "LIMIT 100"
    )
    assert agg_params == {"p0": "2026-01-01", "h1": 5}


async def test_happy_path_count_only_without_group_by(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
        },
        rows=[{"metric_0": 3}],
    )

    assert result.success is True
    assert result.data["total_groups"] == 1
    agg_sql, agg_params = session.executed[1]
    assert _norm(agg_sql) == (
        "SELECT COUNT(*) as metric_0 FROM coll_test_tickets "
        "WHERE title = :p0 LIMIT 100"
    )
    assert agg_params == {"p0": "x"}


async def test_metric_field_id_is_allowed_without_schema_entry(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "max", "field": "id"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
        rows=[{"metric_0": 99}],
    )
    assert result.success is True
    agg_sql, _ = session.executed[1]
    assert "MAX(id) as metric_0" in _norm(agg_sql)


async def test_truncates_results_to_max_result_groups(monkeypatch):
    rows = [{"metric_0": i} for i in range(101)]
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 0}]},
        },
        rows=rows,
    )
    assert result.success is True
    assert len(result.data["results"]) == 100
    assert result.data["total_groups"] == 100


async def test_allow_unfiltered_search_true_permits_no_filters(monkeypatch):
    collection = _collection(allow_unfiltered_search=True)
    result, session = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "metrics": [{"function": "count"}]},
        collection=collection,
        rows=[{"metric_0": 1}],
    )
    assert result.success is True
    agg_sql, _ = session.executed[1]
    assert "WHERE" not in _norm(agg_sql)


# ─────────────────────────────────────────────────────────────────────────────
# Flow: failure branches
# ─────────────────────────────────────────────────────────────────────────────


async def test_collection_not_found(monkeypatch):
    session = _FakeSession()
    _install(monkeypatch, session, None)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    result = await CollectionAggregateTool().v1_0_0(
        ctx, {"collection_slug": "nope", "metrics": [{"function": "count"}]}
    )
    assert result.success is False
    assert result.error == "Collection 'nope' not found"


async def test_slug_mismatch(monkeypatch):
    collection = _collection(slug="other")
    result, _ = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "metrics": [{"function": "count"}]},
        collection=collection,
    )
    assert result.success is False
    assert result.error == "Collection slug mismatch: expected 'tickets', got 'other'"


async def test_no_metrics_rejected(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "At least one metric is required"


async def test_invalid_aggregate_function(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "median", "field": "priority"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Invalid aggregate function: median"


async def test_unknown_metric_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "avg", "field": "nope"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Field 'nope' not found"


async def test_invalid_metric_alias(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count", "alias": "bad-alias"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Invalid metric alias: bad-alias"


async def test_too_many_group_by_fields(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "group_by": ["title", "priority", "opened_at", "meta"],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Maximum 3 group_by fields allowed"


async def test_unknown_group_by_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "group_by": ["nope"],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Group by field 'nope' not found"


async def test_filter_condition_missing_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"and": [{"op": "eq", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Filter condition missing 'field'"


async def test_or_filter_condition_missing_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"or": [{"op": "eq", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Filter condition missing 'field'"


async def test_bare_unknown_filter_key_rejected(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"bogus": 1},
        },
    )
    assert result.success is False
    assert result.error == "Unknown or non-filterable field 'bogus' in filter"


async def test_time_bucket_missing_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
            "time_bucket": {"interval": "day"},
        },
    )
    assert result.success is False
    assert result.error == "time_bucket requires field"


async def test_time_bucket_unknown_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
            "time_bucket": {"field": "nope", "interval": "day"},
        },
    )
    assert result.success is False
    assert result.error == "Field 'nope' not found"


async def test_guardrail_requires_filters(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "metrics": [{"function": "count"}]},
    )
    assert result.success is False
    assert result.error == (
        "Filters are required for aggregate queries on this collection. "
        "Please specify at least one filter condition."
    )


async def test_guardrail_allows_nonempty_dict_with_empty_and_list(monkeypatch):
    # The guardrail checks only `not filters`; {"and": []} is a truthy dict, so
    # it bypasses the unfiltered-aggregate guardrail (unlike the search tool,
    # whose has_filters inspects the "and" list) and the aggregation runs.
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"and": []},
        },
    )
    assert result.success is True
    assert result.data == {"results": [], "total_groups": 0, "collection": "tickets"}


async def test_having_invalid_function(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "group_by": ["priority"],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
            "having": [{"function": "median", "op": "gt", "value": 1}],
        },
    )
    assert result.success is False
    assert result.error == "Invalid HAVING function: median"


async def test_having_unknown_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "group_by": ["priority"],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
            "having": [{"function": "avg", "field": "bogus", "op": "gt", "value": 1}],
        },
    )
    assert result.success is False
    assert result.error == "Field 'bogus' not found"


async def test_unhandled_exception_wrapped(monkeypatch):
    monkeypatch.setattr(
        "app.core.db.get_session_factory",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    result = await CollectionAggregateTool().v1_0_0(
        ctx,
        {
            "collection_slug": "tickets",
            "metrics": [{"function": "count"}],
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 1}]},
        },
    )
    assert result.success is False
    assert result.error == "Aggregate failed: boom"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (direct)
# ─────────────────────────────────────────────────────────────────────────────


def test_is_safe_identifier():
    tool = CollectionAggregateTool()
    assert tool._is_safe_identifier("a_1") is True  # noqa: SLF001
    assert tool._is_safe_identifier("Alias9") is True  # noqa: SLF001
    assert tool._is_safe_identifier("") is False  # noqa: SLF001
    assert tool._is_safe_identifier("1abc") is False  # noqa: SLF001
    assert tool._is_safe_identifier("bad-alias") is False  # noqa: SLF001
    assert tool._is_safe_identifier(None) is False  # noqa: SLF001


def test_allowed_filter_fields_vs_group_fields():
    tool = CollectionAggregateTool()
    collection = _collection()

    filter_fields = tool._allowed_filter_fields(collection)  # noqa: SLF001
    group_fields = tool._allowed_group_fields(collection)  # noqa: SLF001

    # Filterable business fields + id only.
    assert filter_fields == {"title", "priority", "opened_at", "id"}
    # Group fields include every business field (even non-filterable) + id.
    assert group_fields == {"title", "priority", "opened_at", "meta", "code", "id"}


def test_allowed_aggregate_fields_matches_group_fields():
    tool = CollectionAggregateTool()
    collection = _collection()
    assert (
        tool._allowed_aggregate_fields(collection)  # noqa: SLF001
        == tool._allowed_group_fields(collection)  # noqa: SLF001
    )


def test_build_aggregate_sql_passthrough_uses_module_builder_limit():
    tool = CollectionAggregateTool()
    sql, params = tool._build_aggregate_sql(  # noqa: SLF001
        _collection(),
        metrics=[{"function": "count"}],
        group_by=["priority"],
        filters={},
        time_bucket=None,
    )
    assert "GROUP BY priority" in _norm(sql)
    assert _norm(sql).endswith("LIMIT 100")
    assert params == {}


def test_build_condition_passthrough_to_shared_builder():
    tool = CollectionAggregateTool()
    part, params, idx = tool._build_condition(  # noqa: SLF001
        {"field": "priority", "op": "lte", "value": 3}, {}, 0
    )
    assert part == "priority <= :p0"
    assert params == {"p0": 3}
    assert idx == 1


def test_validate_filters_accepts_known_filterable_field():
    tool = CollectionAggregateTool()
    collection = _collection()
    assert (
        tool._validate_filters(  # noqa: SLF001
            collection, {"and": [{"field": "priority", "op": "gte", "value": 1}]}
        )
        is None
    )


def test_validate_time_bucket_accepts_datetime_field():
    tool = CollectionAggregateTool()
    collection = _collection()
    assert (
        tool._validate_time_bucket(  # noqa: SLF001
            collection, {"field": "opened_at", "interval": "week"}
        )
        is None
    )


def test_validate_order_by_accepts_metric_alias_and_group_field():
    tool = CollectionAggregateTool()
    collection = _collection()
    metrics = [{"function": "avg", "field": "priority", "alias": "avg_priority"}]
    assert (
        tool._validate_order_by(collection, metrics, ["priority"], None, "avg_priority")  # noqa: SLF001
        is None
    )
    assert (
        tool._validate_order_by(collection, metrics, ["priority"], None, "-priority")  # noqa: SLF001
        is None
    )


def test_validate_order_by_accepts_time_bucket_alias():
    tool = CollectionAggregateTool()
    collection = _collection()
    metrics = [{"function": "count"}]
    assert (
        tool._validate_order_by(  # noqa: SLF001
            collection, metrics, [], {"field": "opened_at", "interval": "day"}, "time_bucket"
        )
        is None
    )
