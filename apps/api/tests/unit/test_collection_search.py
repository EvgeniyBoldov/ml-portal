"""Unit tests for CollectionSearchTool (collection.search flow and helpers)."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.builtins.collection_search import CollectionSearchTool
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
        "default_sort": {"field": "priority", "order": "desc"},
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
    """Executes SET LOCAL + main SELECT + COUNT; records executed statements."""

    def __init__(self, rows=None, total=0):
        self._rows = rows or []
        self._total = total
        self.executed: list[tuple[str, dict | None]] = []

    async def execute(self, clause, params=None):
        sql = str(clause)
        self.executed.append((sql, params))
        if sql.startswith("SET LOCAL"):
            return _FakeResult(rows=[])
        if sql.startswith("SELECT COUNT(*)"):
            return _FakeResult(scalar=self._total)
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


async def _run(monkeypatch, args, collection=None, rows=None, total=0, not_found=False):
    collection = collection if collection is not None else _collection()
    session = _FakeSession(rows=rows, total=total)
    _install(monkeypatch, session, None if not_found else collection)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    return await CollectionSearchTool().v1_0_0(ctx, args), session


def _norm(sql: str) -> str:
    return " ".join(sql.split())


# ─────────────────────────────────────────────────────────────────────────────
# Flow: happy paths
# ─────────────────────────────────────────────────────────────────────────────


async def test_happy_path_filters_query_sort_pagination(monkeypatch):
    rows = [
        {"id": 1, "title": "Network down", "status": "open", "priority": 3, "meta": {"a": 1}}
    ]
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "query": "network",
            "filters": {"and": [{"field": "priority", "op": "gte", "value": 2}]},
            "limit": 10,
            "offset": 2,
        },
        rows=rows,
        total=5,
    )

    assert result.success is True
    data = result.data
    assert data["total"] == 5
    assert data["returned"] == 1
    assert data["has_more"] is True
    assert data["collection"] == "tickets"
    assert data["rows"][0]["title"] == "Network down"

    assert len(session.executed) == 3
    timeout_sql, _ = session.executed[0]
    assert timeout_sql == "SET LOCAL statement_timeout = '10s'"

    sql, params = session.executed[1]
    assert _norm(sql) == (
        "SELECT * FROM coll_test_tickets "
        "WHERE priority >= :p0 AND (title ILIKE :query_1 OR status ILIKE :query_1) "
        "ORDER BY priority DESC LIMIT 10 OFFSET 2"
    )
    assert params == {"p0": 2, "query_1": "%network%"}

    count_sql, count_params = session.executed[2]
    assert _norm(count_sql) == (
        "SELECT COUNT(*) FROM coll_test_tickets "
        "WHERE priority >= :p0 AND (title ILIKE :query_1 OR status ILIKE :query_1)"
    )
    assert count_params == {"p0": 2, "query_1": "%network%"}


async def test_happy_path_has_more_false(monkeypatch):
    rows = [{"id": 2, "title": "Last", "status": "open", "priority": 2}]
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "Last"}]},
            "limit": 10,
            "offset": 2,
        },
        rows=rows,
        total=3,
    )
    assert result.success is True
    assert result.data["has_more"] is False
    assert result.data["total"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# Flow: sort normalization
# ─────────────────────────────────────────────────────────────────────────────


async def test_sort_string_with_explicit_order(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "sort": "priority ASC",
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("ORDER BY priority ASC LIMIT 50 OFFSET 0")


async def test_sort_string_single_word_defaults_desc(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "sort": "title",
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("ORDER BY title DESC LIMIT 50 OFFSET 0")


async def test_sort_string_blank_falls_back_to_default_sort(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "sort": "   ",
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("ORDER BY priority DESC LIMIT 50 OFFSET 0")


async def test_sort_list_of_dicts_lowercases_order(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "sort": [{"field": "priority", "order": "DESC"}],
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("ORDER BY priority DESC LIMIT 50 OFFSET 0")


async def test_sort_list_of_strings_is_rejected(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "sort": ["priority", "desc"],
        },
        rows=[],
    )
    assert result.success is False
    assert result.error == "Search failed: 'str' object has no attribute 'get'"


# ─────────────────────────────────────────────────────────────────────────────
# Flow: limit / offset guardrails
# ─────────────────────────────────────────────────────────────────────────────


async def test_limit_invalid_falls_back_to_default(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "limit": "abc",
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("LIMIT 50 OFFSET 0")


async def test_limit_capped_at_hard_max(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "limit": 1000,
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("LIMIT 100 OFFSET 0")


async def test_limit_capped_by_collection_max_limit(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "limit": 50,
        },
        collection=_collection(max_limit=25),
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("LIMIT 25 OFFSET 0")


async def test_offset_invalid_defaults_to_zero(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "offset": "bad",
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("LIMIT 50 OFFSET 0")


async def test_offset_capped_at_hard_max(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
            "offset": 5000,
        },
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]).endswith("LIMIT 50 OFFSET 1000")


# ─────────────────────────────────────────────────────────────────────────────
# Flow: unfiltered-search guardrail
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filters",
    [{}, {"and": []}, {"bogus": 1}],
    ids=["empty", "empty-and-list", "unknown-key"],
)
async def test_guardrail_blocks_unfiltered_search(monkeypatch, filters):
    result, _ = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "filters": filters},
        rows=[],
    )
    assert result.success is False
    assert result.error == (
        "Filters or query are required for this collection. "
        "Please specify at least one filter condition or search query."
    )


async def test_allow_unfiltered_search_permits_empty_filters(monkeypatch):
    result, session = await _run(
        monkeypatch,
        {"collection_slug": "tickets"},
        collection=_collection(allow_unfiltered_search=True),
        rows=[],
    )
    assert result.success is True
    assert _norm(session.executed[1][0]) == (
        "SELECT * FROM coll_test_tickets ORDER BY priority DESC LIMIT 50 OFFSET 0"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Flow: failure branches
# ─────────────────────────────────────────────────────────────────────────────


async def test_collection_not_found(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]}},
        rows=[],
        not_found=True,
    )
    assert result.success is False
    assert result.error == "Collection 'tickets' not found"


async def test_collection_slug_mismatch(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]}},
        collection=_collection(slug="other"),
        rows=[],
    )
    assert result.success is False
    assert result.error == "Collection slug mismatch: expected 'tickets', got 'other'"


@pytest.mark.parametrize(
    "filters",
    [
        {"and": [{"field": "meta", "op": "eq", "value": 1}]},
        {"or": [{"field": "meta", "op": "eq", "value": 1}]},
    ],
    ids=["and-branch", "or-branch"],
)
async def test_filter_validation_unknown_field(monkeypatch, filters):
    result, _ = await _run(
        monkeypatch,
        {"collection_slug": "tickets", "filters": filters},
        rows=[],
    )
    assert result.success is False
    assert result.error == "Unknown field 'meta' in filter"


async def test_filter_validation_missing_field(monkeypatch):
    result, _ = await _run(
        monkeypatch,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"op": "eq", "value": "x"}]},
        },
        rows=[],
    )
    assert result.success is False
    assert result.error == "Filter condition missing 'field'"


async def test_unhandled_exception_wrapped(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(
        "app.core.db.get_session_factory", lambda: lambda: _SessionContext(session)
    )
    monkeypatch.setattr(
        CollectionService, "get_by_slug", AsyncMock(side_effect=RuntimeError("boom"))
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    result = await CollectionSearchTool().v1_0_0(
        ctx,
        {
            "collection_slug": "tickets",
            "filters": {"and": [{"field": "title", "op": "eq", "value": "x"}]},
        },
    )
    assert result.success is False
    assert result.error == "Search failed: boom"


# ─────────────────────────────────────────────────────────────────────────────
# Direct: _build_search_sql
# ─────────────────────────────────────────────────────────────────────────────


def test_build_search_sql_no_where_no_order():
    tool = CollectionSearchTool()
    collection = _collection(default_sort=None)
    sql, params = tool._build_search_sql(collection, {}, None, [], 10, 0)
    assert _norm(sql) == "SELECT * FROM coll_test_tickets LIMIT 10 OFFSET 0"
    assert params == {}


def test_build_search_sql_query_only():
    tool = CollectionSearchTool()
    collection = _collection()
    sql, params = tool._build_search_sql(collection, {}, "net", [], 10, 0)
    assert _norm(sql) == (
        "SELECT * FROM coll_test_tickets "
        "WHERE (title ILIKE :query_0 OR status ILIKE :query_0) "
        "ORDER BY priority DESC LIMIT 10 OFFSET 0"
    )
    assert params == {"query_0": "%net%"}


def test_build_search_sql_or_filters_grouped():
    tool = CollectionSearchTool()
    collection = _collection(default_sort=None)
    filters = {
        "or": [
            {"field": "status", "op": "eq", "value": "open"},
            {"field": "priority", "op": "lt", "value": 3},
        ]
    }
    sql, params = tool._build_search_sql(collection, filters, None, [], 10, 0)
    assert _norm(sql) == (
        "SELECT * FROM coll_test_tickets "
        "WHERE (status = :p0 OR priority < :p1) "
        "LIMIT 10 OFFSET 0"
    )
    assert params == {"p0": "open", "p1": 3}


def test_build_search_sql_multiple_and_filters():
    tool = CollectionSearchTool()
    collection = _collection(default_sort=None)
    filters = {
        "and": [
            {"field": "priority", "op": "gte", "value": 2},
            {"field": "status", "op": "eq", "value": "open"},
        ]
    }
    sql, params = tool._build_search_sql(collection, filters, None, [], 10, 0)
    assert _norm(sql) == (
        "SELECT * FROM coll_test_tickets "
        "WHERE priority >= :p0 AND status = :p1 "
        "LIMIT 10 OFFSET 0"
    )
    assert params == {"p0": 2, "p1": "open"}


def test_build_search_sql_or_branch_with_only_invalid_conditions_is_dropped():
    tool = CollectionSearchTool()
    collection = _collection(default_sort=None)
    filters = {
        "and": [{"field": "priority", "op": "gte", "value": 2}],
        "or": [{"op": "eq", "value": 1}],
    }
    sql, _ = tool._build_search_sql(collection, filters, None, [], 10, 0)
    assert _norm(sql) == (
        "SELECT * FROM coll_test_tickets WHERE priority >= :p0 LIMIT 10 OFFSET 0"
    )


def test_build_search_sql_sort_defaults_asc():
    tool = CollectionSearchTool()
    collection = _collection(default_sort=None)
    sql, _ = tool._build_search_sql(
        collection, {}, None, [{"field": "title"}], 10, 0
    )
    assert _norm(sql).endswith("ORDER BY title ASC LIMIT 10 OFFSET 0")


@pytest.mark.parametrize(
    "sort,expected",
    [
        ([{"field": "created_at", "order": "desc"}], "_created_at DESC"),
        ([{"field": "updated_at", "order": "asc"}], "_updated_at ASC"),
        ([{"field": "id", "order": "desc"}], "id DESC"),
    ],
    ids=["created_at-alias", "updated_at-alias", "id"],
)
def test_build_search_sql_sort_system_columns(sort, expected):
    tool = CollectionSearchTool()
    collection = _collection(default_sort=None)
    sql, _ = tool._build_search_sql(collection, {}, None, sort, 10, 0)
    assert _norm(sql).endswith(f"ORDER BY {expected} LIMIT 10 OFFSET 0")


def test_build_search_sql_sort_unknown_field_falls_back_to_default_sort():
    tool = CollectionSearchTool()
    collection = _collection()
    sql, _ = tool._build_search_sql(
        collection, {}, None, [{"field": "meta", "order": "asc"}], 10, 0
    )
    assert _norm(sql).endswith("ORDER BY priority DESC LIMIT 10 OFFSET 0")


def test_build_search_sql_sort_invalid_order_falls_back_to_default_sort():
    tool = CollectionSearchTool()
    collection = _collection()
    sql, _ = tool._build_search_sql(
        collection, {}, None, [{"field": "priority", "order": "sideways"}], 10, 0
    )
    assert _norm(sql).endswith("ORDER BY priority DESC LIMIT 10 OFFSET 0")


# ─────────────────────────────────────────────────────────────────────────────
# Direct: _build_count_sql
# ─────────────────────────────────────────────────────────────────────────────


def test_build_count_sql_without_conditions():
    tool = CollectionSearchTool()
    sql, params = tool._build_count_sql(_collection(), {}, None)
    assert _norm(sql) == "SELECT COUNT(*) FROM coll_test_tickets"
    assert params == {}


def test_build_count_sql_with_conditions():
    tool = CollectionSearchTool()
    filters = {"and": [{"field": "priority", "op": "gte", "value": 2}]}
    # Count SQL restarts its own param counter, but filter conditions consume
    # indices before the query param: filter -> p0, query -> query_1.
    sql, params = tool._build_count_sql(_collection(), filters, "net")
    assert _norm(sql) == (
        "SELECT COUNT(*) FROM coll_test_tickets "
        "WHERE priority >= :p0 AND (title ILIKE :query_1 OR status ILIKE :query_1)"
    )
    assert params == {"p0": 2, "query_1": "%net%"}


# ─────────────────────────────────────────────────────────────────────────────
# Direct: _validate_filters
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_filters_empty():
    assert CollectionSearchTool()._validate_filters(_collection(), {}) is None


@pytest.mark.parametrize(
    "filters",
    [
        {"and": [{"field": "id", "op": "eq", "value": "abc"}]},
        {"and": [{"field": "title", "op": "like", "value": "x"}]},
        {"and": [{"field": "title"}], "or": [{"field": "status", "op": "eq", "value": "open"}]},
    ],
    ids=["id-always-allowed", "known-field", "and-and-or"],
)
def test_validate_filters_accepts_known_fields(filters):
    assert CollectionSearchTool()._validate_filters(_collection(), filters) is None


def test_validate_filters_or_branch_missing_field():
    filters = {"or": [{"op": "eq", "value": "x"}]}
    assert (
        CollectionSearchTool()._validate_filters(_collection(), filters)
        == "Filter condition missing 'field'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Direct: _build_condition (ops beyond in/not_in list expansion)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "op,sql_fragment,value,param",
    [
        ("eq", "title = :p0", "x", "x"),
        ("neq", "title != :p0", "x", "x"),
        ("gt", "priority > :p0", 5, 5),
        ("gte", "priority >= :p0", 5, 5),
        ("lt", "priority < :p0", 5, 5),
        ("lte", "priority <= :p0", 5, 5),
        ("like", "title ILIKE :p0", "net", "%net%"),
        ("contains", "title ILIKE :p0", "net", "%net%"),
    ],
)
def test_build_condition_parametrized_ops(op, sql_fragment, value, param):
    part, params, idx = CollectionSearchTool()._build_condition(
        {"field": sql_fragment.split()[0], "op": op, "value": value}, {}, 0
    )
    assert part == sql_fragment
    assert params == {"p0": param}
    assert idx == 1


def test_build_condition_range_full():
    part, params, idx = CollectionSearchTool()._build_condition(
        {"field": "priority", "op": "range", "value": {"gte": 1, "lt": 5}}, {}, 0
    )
    assert part == "(priority >= :p0_gte AND priority < :p0_lt)"
    assert params == {"p0_gte": 1, "p0_lt": 5}
    assert idx == 1


def test_build_condition_range_partial():
    part, params, _ = CollectionSearchTool()._build_condition(
        {"field": "priority", "op": "range", "value": {"lte": 3}}, {}, 0
    )
    assert part == "(priority <= :p0_lte)"
    assert params == {"p0_lte": 3}


def test_build_condition_range_non_dict_value_yields_empty():
    part, params, idx = CollectionSearchTool()._build_condition(
        {"field": "priority", "op": "range", "value": 5}, {}, 0
    )
    assert part == ""
    assert params == {}
    assert idx == 1


@pytest.mark.parametrize("value,expected", [(True, "IS NULL"), (False, "IS NOT NULL")])
def test_build_condition_is_null(value, expected):
    part, params, _ = CollectionSearchTool()._build_condition(
        {"field": "title", "op": "is_null", "value": value}, {}, 0
    )
    assert part == f"title {expected}"
    assert params == {}


def test_build_condition_in_scalar_value_is_wrapped():
    part, params, _ = CollectionSearchTool()._build_condition(
        {"field": "status", "op": "in", "value": "open"}, {}, 0
    )
    assert part == "status IN (:p0_0)"
    assert params == {"p0_0": "open"}


def test_build_condition_in_empty_list_yields_empty():
    part, params, _ = CollectionSearchTool()._build_condition(
        {"field": "status", "op": "in", "value": []}, {}, 0
    )
    assert part == ""
    assert params == {}


def test_build_condition_not_in_scalar_value_is_wrapped():
    part, params, _ = CollectionSearchTool()._build_condition(
        {"field": "status", "op": "not_in", "value": "closed"}, {}, 0
    )
    assert part == "status NOT IN (:p0_0)"
    assert params == {"p0_0": "closed"}


def test_build_condition_unknown_op_yields_empty():
    part, params, idx = CollectionSearchTool()._build_condition(
        {"field": "title", "op": "regex", "value": "x"}, {}, 0
    )
    assert part == ""
    assert params == {}
    assert idx == 1


def test_build_condition_missing_field_yields_empty():
    part, params, idx = CollectionSearchTool()._build_condition(
        {"op": "eq", "value": "x"}, {}, 0
    )
    assert part == ""
    assert params == {}
    assert idx == 0


# ─────────────────────────────────────────────────────────────────────────────
# Direct: _format_rows
# ─────────────────────────────────────────────────────────────────────────────


def test_format_rows_converts_uuids():
    tool = CollectionSearchTool()
    row_id, title_uuid = uuid4(), uuid4()
    out = tool._format_rows(
        [{"id": row_id, "title": title_uuid, "status": "open", "priority": 1}],
        _collection(),
    )
    assert out[0]["id"] == str(row_id)
    assert out[0]["title"] == str(title_uuid)


def test_format_rows_preserves_int_id_and_json():
    tool = CollectionSearchTool()
    out = tool._format_rows(
        [{"id": 7, "title": "t", "meta": {"a": 1}}], _collection()
    )
    assert out[0]["id"] == 7
    assert isinstance(out[0]["id"], int)
    assert out[0]["meta"] == {"a": 1}


def test_format_rows_truncates_long_text_fields():
    tool = CollectionSearchTool()
    out = tool._format_rows([{"id": 1, "title": "x" * 600}], _collection())
    assert out[0]["title"] == "x" * 497 + "..."
    assert len(out[0]["title"]) == 500


def test_format_rows_does_not_truncate_string_fields():
    tool = CollectionSearchTool()
    out = tool._format_rows([{"id": 1, "code": "y" * 600}], _collection())
    assert out[0]["code"] == "y" * 600


def test_format_rows_skips_non_field_keys():
    tool = CollectionSearchTool()
    out = tool._format_rows(
        [{"id": 1, "title": "t", "_created_at": "2026-01-01", "unknown_col": 5}],
        _collection(),
    )
    assert "_created_at" not in out[0]
    assert "unknown_col" not in out[0]
    assert out[0]["title"] == "t"


def test_format_rows_missing_id_key():
    tool = CollectionSearchTool()
    out = tool._format_rows([{"title": "t"}], _collection())
    assert "id" not in out[0]
    assert out[0]["title"] == "t"


def test_format_rows_decimal_left_as_is():
    tool = CollectionSearchTool()
    out = tool._format_rows([{"id": 1, "priority": Decimal("3.5")}], _collection())
    assert out[0]["priority"] == Decimal("3.5")
