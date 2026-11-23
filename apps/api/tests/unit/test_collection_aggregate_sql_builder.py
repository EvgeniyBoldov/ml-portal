"""Unit tests for CollectionAggregateSQLBuilder (collection.aggregate SQL generation)."""
from __future__ import annotations

import pytest

from app.agents.builtins.collection_aggregate_sql_builder import (
    CollectionAggregateSQLBuilder,
)


def _builder(max_result_groups: int = 7) -> CollectionAggregateSQLBuilder:
    return CollectionAggregateSQLBuilder(
        max_result_groups=max_result_groups,
        allowed_functions={"count", "count_distinct", "sum", "avg", "min", "max"},
    )


def _collection(**overrides):
    from types import SimpleNamespace

    attrs = {"table_name": "coll_test_tickets"}
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


def _norm(sql: str) -> str:
    return " ".join(sql.split())


# ─────────────────────────────────────────────────────────────────────────────
# build_aggregate_sql
# ─────────────────────────────────────────────────────────────────────────────


def test_build_aggregate_sql_count_only_without_group_by():
    sql, params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count"}],
        group_by=[],
        filters={},
        time_bucket=None,
    )

    assert params == {}
    assert _norm(sql) == "SELECT COUNT(*) as metric_0 FROM coll_test_tickets LIMIT 7"


def test_build_aggregate_sql_renders_every_metric_function_and_alias():
    sql, params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[
            {"function": "count"},
            {"function": "count", "field": "title"},
            {"function": "count_distinct", "field": "title", "alias": "uniq_titles"},
            {"function": "sum", "field": "priority"},
            {"function": "avg", "field": "priority"},
            {"function": "min", "field": "opened_at"},
            {"function": "max", "field": "opened_at"},
        ],
        group_by=["priority"],
        filters={},
        time_bucket=None,
    )

    assert params == {}
    normalized = _norm(sql)
    assert "SELECT priority, COUNT(*) as metric_0, COUNT(title) as metric_1," in normalized
    assert "COUNT(DISTINCT title) as uniq_titles" in normalized
    assert "SUM(priority) as metric_3" in normalized
    assert "AVG(priority) as metric_4" in normalized
    assert "MIN(opened_at) as metric_5" in normalized
    assert "MAX(opened_at) as metric_6" in normalized
    assert "GROUP BY priority" in normalized
    # Default order is the first group_by field when no order_by is given.
    assert "ORDER BY priority" in normalized
    assert "LIMIT 7" in normalized


def test_build_aggregate_sql_skips_unknown_function_metric_silently():
    # Validation of allowed functions happens in the tool; the builder renders
    # nothing for unknown functions (fall-through) instead of raising.
    sql, _params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "median", "field": "priority"}],
        group_by=[],
        filters={},
        time_bucket=None,
    )

    assert _norm(sql) == "SELECT FROM coll_test_tickets LIMIT 7"


@pytest.mark.parametrize(
    "interval",
    ["hour", "day", "week", "month", "year", None, "decade"],
)
def test_build_aggregate_sql_time_bucket_intervals(interval):
    expected = interval if interval in {"hour", "day", "week", "month", "year"} else "day"
    time_bucket = {"field": "opened_at"}
    if interval is not None:
        time_bucket["interval"] = interval

    sql, _params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count"}],
        group_by=["priority"],
        filters={},
        time_bucket=time_bucket,
    )

    normalized = _norm(sql)
    assert f"date_trunc('{expected}', opened_at) as time_bucket" in normalized
    assert f"GROUP BY priority, date_trunc('{expected}', opened_at)" in normalized


def test_build_aggregate_sql_time_bucket_field_already_in_group_by_not_duplicated():
    sql, _params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count"}],
        group_by=["opened_at"],
        filters={},
        time_bucket={"field": "opened_at", "interval": "month"},
    )

    normalized = _norm(sql)
    # date_trunc appears once (SELECT only); GROUP BY keeps the plain field
    # because the builder skips appending the expression when already grouped.
    assert normalized.count("date_trunc('month', opened_at)") == 1
    assert "GROUP BY opened_at ORDER BY opened_at" in normalized


@pytest.mark.parametrize(
    "order_by,expected",
    [
        ("-metric_0", "ORDER BY metric_0 DESC"),
        ("metric_0", "ORDER BY metric_0 ASC"),
    ],
)
def test_build_aggregate_sql_order_by_direction(order_by, expected):
    sql, _params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count"}],
        group_by=["priority"],
        filters={},
        time_bucket=None,
        order_by=order_by,
    )

    assert expected in _norm(sql)


def test_build_aggregate_sql_no_order_clause_without_group_by_or_order_by():
    sql, _params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count"}],
        group_by=[],
        filters={},
        time_bucket=None,
    )

    assert "ORDER BY" not in sql


def test_build_aggregate_sql_full_query_with_where_having_and_time_bucket():
    sql, params = _builder(max_result_groups=100).build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count", "alias": "cnt"}],
        group_by=["priority"],
        filters={
            "and": [{"field": "opened_at", "op": "gte", "value": "2026-01-01"}],
            "or": [{"field": "title", "op": "like", "value": "net"}],
            "status": "open",
        },
        time_bucket={"field": "opened_at", "interval": "week"},
        having=[{"function": "count", "op": "gt", "value": 1}],
        order_by="-cnt",
    )

    normalized = _norm(sql)
    assert (
        "SELECT priority, date_trunc('week', opened_at) as time_bucket, "
        "COUNT(*) as cnt FROM coll_test_tickets" in normalized
    )
    assert "WHERE opened_at >= :p0" in normalized
    assert "(title ILIKE :p1)" in normalized
    assert "status = :p2" in normalized
    assert "GROUP BY priority, date_trunc('week', opened_at)" in normalized
    assert "HAVING COUNT(*) > :h3" in normalized
    assert "ORDER BY cnt DESC" in normalized
    assert "LIMIT 100" in normalized
    assert params == {
        "p0": "2026-01-01",
        "p1": "%net%",
        "p2": "open",
        "h3": 1,
    }


def test_build_aggregate_sql_having_ignored_without_group_by():
    sql, params = _builder().build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count"}],
        group_by=[],
        filters={},
        time_bucket=None,
        having=[{"function": "count", "op": "gt", "value": 1}],
    )

    assert "HAVING" not in sql
    assert params == {}


# ─────────────────────────────────────────────────────────────────────────────
# build_where_clause
# ─────────────────────────────────────────────────────────────────────────────


def test_build_where_clause_empty_filters_returns_nothing():
    parts, params, idx = _builder().build_where_clause({}, {}, 0)

    assert parts == []
    assert params == {}
    assert idx == 0


def test_build_where_clause_combines_and_or_and_bare_keys():
    parts, params, idx = _builder().build_where_clause(
        {
            "and": [{"field": "priority", "op": "eq", "value": 1}],
            "or": [
                {"field": "title", "op": "eq", "value": "a"},
                {"field": "title", "op": "eq", "value": "b"},
            ],
            "status": "open",
        },
        {},
        0,
    )

    assert parts == [
        "priority = :p0",
        "(title = :p1 OR title = :p2)",
        "status = :p3",
    ]
    assert params == {"p0": 1, "p1": "a", "p2": "b", "p3": "open"}
    assert idx == 4


def test_build_where_clause_or_conditions_dropped_when_all_empty():
    parts, params, idx = _builder().build_where_clause(
        {"or": [{"field": "priority", "op": "in", "value": []}]},
        {"existing": 1},
        5,
    )

    assert parts == []
    assert params == {"existing": 1}
    # The param counter still advances for the consumed (empty) condition.
    assert idx == 6


# ─────────────────────────────────────────────────────────────────────────────
# build_condition
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cond,expected_sql,expected_params",
    [
        ({"field": "priority", "op": "eq", "value": 1}, "priority = :p0", {"p0": 1}),
        ({"field": "priority", "op": "neq", "value": 2}, "priority != :p0", {"p0": 2}),
        ({"field": "priority"}, "priority = :p0", {"p0": None}),
        ({"field": "priority", "op": "gt", "value": 1}, "priority > :p0", {"p0": 1}),
        ({"field": "priority", "op": "gte", "value": 1}, "priority >= :p0", {"p0": 1}),
        ({"field": "priority", "op": "lt", "value": 9}, "priority < :p0", {"p0": 9}),
        ({"field": "priority", "op": "lte", "value": 9}, "priority <= :p0", {"p0": 9}),
        (
            {"field": "priority", "op": "in", "value": [1, 2]},
            "priority IN (:p0_0, :p0_1)",
            {"p0_0": 1, "p0_1": 2},
        ),
        (
            {"field": "priority", "op": "in", "value": 5},
            "priority IN (:p0_0)",
            {"p0_0": 5},
        ),
        (
            {"field": "priority", "op": "not_in", "value": [4]},
            "priority NOT IN (:p0_0)",
            {"p0_0": 4},
        ),
        (
            {"field": "title", "op": "like", "value": "net"},
            "title ILIKE :p0",
            {"p0": "%net%"},
        ),
        (
            {"field": "title", "op": "contains", "value": "net"},
            "title ILIKE :p0",
            {"p0": "%net%"},
        ),
        ({"field": "title", "op": "is_null", "value": True}, "title IS NULL", {}),
        ({"field": "title", "op": "is_null", "value": False}, "title IS NOT NULL", {}),
        (
            {"field": "opened_at", "op": "range", "value": {"gte": 1, "lt": 10}},
            "(opened_at >= :p0_gte AND opened_at < :p0_lt)",
            {"p0_gte": 1, "p0_lt": 10},
        ),
        (
            {"field": "opened_at", "op": "range", "value": {"gt": 0, "lte": 5}},
            "(opened_at > :p0_gt AND opened_at <= :p0_lte)",
            {"p0_gt": 0, "p0_lte": 5},
        ),
        ({"field": "opened_at", "op": "range", "value": {}}, "", {}),
        ({"field": "priority", "op": "regex", "value": "x"}, "", {}),
    ],
)
def test_build_condition_ops(cond, expected_sql, expected_params):
    sql, params, idx = _builder().build_condition(cond, {}, 0)

    assert sql == expected_sql
    assert params == expected_params
    assert idx == 1


def test_build_condition_in_with_empty_list_returns_empty_and_consumes_index():
    sql, params, idx = _builder().build_condition(
        {"field": "priority", "op": "in", "value": []}, {}, 3
    )

    assert sql == ""
    assert params == {}
    assert idx == 4


def test_build_condition_missing_field_returns_empty_without_consuming_index():
    sql, params, idx = _builder().build_condition({"op": "eq", "value": 1}, {}, 7)

    assert sql == ""
    assert params == {}
    assert idx == 7


def test_build_condition_range_with_non_dict_value_raises_type_error():
    # FIXME(known issue): op="range" with a non-dict value raises TypeError
    # ("argument of type 'int' is not iterable") because the builder performs
    # `"gte" in value` without validating the value shape; the tool-level
    # validation does not catch this either. Test pins current behavior.
    with pytest.raises(TypeError):
        _builder().build_condition(
            {"field": "opened_at", "op": "range", "value": 5}, {}, 0
        )


# ─────────────────────────────────────────────────────────────────────────────
# build_having_clause
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cond,expected",
    [
        ({"function": "count", "op": "gt", "value": 1}, "COUNT(*) > :h0"),
        ({"function": "count", "field": "title", "op": "lte", "value": 2}, "COUNT(title) <= :h0"),
        ({"function": "count", "op": "eq", "value": 3}, "COUNT(*) = :h0"),
        ({"function": "count", "op": "neq", "value": 3}, "COUNT(*) != :h0"),
        ({"function": "count", "op": "lt", "value": 3}, "COUNT(*) < :h0"),
        ({"function": "count", "op": "gte", "value": 3}, "COUNT(*) >= :h0"),
        ({"function": "count_distinct", "field": "title", "op": "gt", "value": 1}, "COUNT(DISTINCT title) > :h0"),
        ({"function": "sum", "field": "priority", "op": "gt", "value": 10}, "SUM(priority) > :h0"),
        ({"function": "avg", "field": "priority", "op": "gt", "value": 0.5}, "AVG(priority) > :h0"),
        ({"function": "min", "field": "opened_at", "op": "gt", "value": 0}, "MIN(opened_at) > :h0"),
        ({"function": "max", "field": "opened_at", "op": "gt", "value": 0}, "MAX(opened_at) > :h0"),
    ],
)
def test_build_having_clause_supported_conditions(cond, expected):
    parts, params, idx = _builder().build_having_clause([cond], {}, 0)

    assert parts == [expected]
    assert params == {"h0": cond["value"]}
    assert idx == 1


@pytest.mark.parametrize(
    "cond",
    [
        {"function": "median", "field": "priority", "op": "gt", "value": 1},  # not allowed
        {"function": "count", "op": "like", "value": 1},  # unsupported op
        {"function": "count", "op": None, "value": 1},  # unknown op
        {"function": "count_distinct", "op": "gt", "value": 1},  # field required
        {"function": "sum", "op": "gt", "value": 1},  # field required
        {"function": "avg", "op": "gt", "value": 1},  # field required
        {"function": "min", "op": "gt", "value": 1},  # field required
        {"function": "max", "op": "gt", "value": 1},  # field required
    ],
)
def test_build_having_clause_skips_invalid_conditions(cond):
    parts, params, idx = _builder().build_having_clause([cond], {}, 0)

    assert parts == []
    assert params == {}
    assert idx == 0


def test_build_having_clause_skips_allowed_but_unhandled_function():
    # Defensive branch: the tool injects allowed_functions == exactly the six
    # functions the builder renders, so this is only reachable with a builder
    # configured with an extra allowed function, which is silently skipped.
    builder = CollectionAggregateSQLBuilder(
        max_result_groups=7,
        allowed_functions={"count", "median"},
    )
    parts, params, idx = builder.build_having_clause(
        [
            {"function": "median", "field": "priority", "op": "gt", "value": 1},
            {"function": "count", "op": "gt", "value": 2},
        ],
        {},
        0,
    )

    assert parts == ["COUNT(*) > :h0"]
    assert params == {"h0": 2}
    assert idx == 1


def test_build_having_clause_multiple_conditions_share_param_counter():
    parts, params, idx = _builder().build_having_clause(
        [
            {"function": "count", "op": "gt", "value": 1},
            {"function": "avg", "field": "priority", "op": "lte", "value": 5},
        ],
        {},
        2,
    )

    assert parts == ["COUNT(*) > :h2", "AVG(priority) <= :h3"]
    assert params == {"h2": 1, "h3": 5}
    assert idx == 4


def test_builder_converts_arguments_to_typed_values():
    builder = CollectionAggregateSQLBuilder(
        max_result_groups="12",
        allowed_functions=["count"],
    )

    assert builder.max_result_groups == 12
    assert builder.allowed_functions == {"count"}
    assert "LIMIT 12" in builder.build_aggregate_sql(
        collection=_collection(),
        metrics=[{"function": "count"}],
        group_by=[],
        filters={},
        time_bucket=None,
    )[0]
