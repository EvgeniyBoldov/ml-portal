"""Unit tests for CollectionRowService (row-level data access).

Uses a scripted fake AsyncSession that dispatches on normalized SQL text
so no real database is needed. Validates SQL shape, bind parameters,
sort resolution, vector cleanup wiring and serialization contracts.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError, RowValidationError
from app.models.collection import Collection, CollectionType, FieldType
from app.services.collection.row_service import CollectionRowService


TENANT_ID = uuid4()
INSTANCE_ID = uuid4()
ROW_ID = uuid4()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeMappings:
    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def all(self) -> list:
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def one(self):
        return self._rows[0]


class FakeResult:
    def __init__(
        self,
        *,
        rows: list | None = None,
        scalar: Any = None,
        scalar_one: Any = None,
        scalar_one_or_none: Any = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar
        self._scalar_one = scalar_one
        self._scalar_one_or_none = scalar_one_or_none
        self.rowcount = rowcount

    def mappings(self) -> FakeMappings:
        return FakeMappings(self._rows)

    def scalar(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar_one

    def scalar_one_or_none(self):
        return self._scalar_one_or_none

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    def __init__(self) -> None:
        self.handlers: list[tuple[str, Any]] = []
        self.calls: list[tuple[str, dict | None]] = []
        self.flush_count = 0

    def on(self, substr: str, result: Any) -> None:
        self.handlers.append((substr, result))

    async def execute(self, stmt, params: dict | None = None):
        sql = " ".join(str(stmt).split())
        self.calls.append((sql, params))
        for substr, result in self.handlers:
            if substr in sql:
                if isinstance(result, BaseException):
                    raise result
                return result
        return FakeResult()

    async def flush(self) -> None:
        self.flush_count += 1


def make_collection(
    fields: list | None = None,
    **overrides: Any,
) -> Collection:
    base: dict[str, Any] = dict(
        tenant_id=TENANT_ID,
        slug="orders",
        name="Orders",
        collection_type=CollectionType.TABLE.value,
        data_instance_id=INSTANCE_ID,
        table_name="coll_orders",
        total_rows=0,
        default_sort=None,
        time_column=None,
    )
    base.update(overrides)
    if fields is None:
        fields = [
            {
                "name": "title",
                "category": "user",
                "data_type": FieldType.STRING.value,
                "required": True,
                "filterable": True,
                "sortable": True,
            },
            {
                "name": "amount",
                "category": "user",
                "data_type": FieldType.INTEGER.value,
                "required": False,
                "filterable": True,
                "sortable": False,
            },
            {
                "name": "created",
                "category": "user",
                "data_type": FieldType.DATETIME.value,
                "required": False,
                "filterable": True,
                "sortable": True,
            },
            {
                "name": "notes",
                "category": "user",
                "data_type": FieldType.TEXT.value,
                "required": False,
                "filterable": False,
                "sortable": False,
            },
        ]
    collection = Collection(**base)
    collection.fields = fields
    return collection


def vector_fields() -> list[dict]:
    return [
        {
            "name": "body",
            "category": "user",
            "data_type": FieldType.TEXT.value,
            "required": False,
            "filterable": False,
            "sortable": False,
            "used_in_retrieval": True,
        }
    ]


# ---------------------------------------------------------------------------
# _require_table_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table_name", [None, "", "   "])
def test_require_table_name_rejects_missing(table_name):
    collection = make_collection(table_name=table_name)
    with pytest.raises(AppError, match="storage table is not configured"):
        CollectionRowService._require_table_name(collection)


def test_require_table_name_strips_whitespace():
    collection = make_collection(table_name="  coll_x  ")
    assert CollectionRowService._require_table_name(collection) == "coll_x"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_row_by_id_returns_public_fields_only():
    session = FakeSession()
    session.on(
        "SELECT * FROM coll_orders WHERE id = :row_id",
        FakeResult(
            rows=[
                {
                    "id": ROW_ID,
                    "title": "abc",
                    "amount": 5,
                    "notes": "n",
                    "_created_at": "2026-01-01",
                }
            ]
        ),
    )
    collection = make_collection()
    row = await CollectionRowService(session).get_row_by_id(collection, ROW_ID)
    assert row == {"id": ROW_ID, "title": "abc", "amount": 5, "notes": "n"}
    sql, params = session.calls[0]
    assert "FROM coll_orders" in sql
    assert params == {"row_id": ROW_ID}


@pytest.mark.asyncio
async def test_get_row_by_id_missing_returns_none():
    session = FakeSession()
    session.on("SELECT * FROM coll_orders", FakeResult(rows=[]))
    collection = make_collection()
    assert await CollectionRowService(session).get_row_by_id(collection, ROW_ID) is None


@pytest.mark.asyncio
async def test_search_without_filters_uses_true_and_id_sort():
    session = FakeSession()
    session.on("SELECT * FROM coll_orders", FakeResult(rows=[]))
    collection = make_collection()
    await CollectionRowService(session).search(collection, limit=10, offset=5)
    sql, params = session.calls[0]
    assert "WHERE TRUE" in sql
    assert "ORDER BY id DESC" in sql
    assert "LIMIT :limit OFFSET :offset" in sql
    assert params["limit"] == 10
    assert params["offset"] == 5


@pytest.mark.asyncio
async def test_search_query_builds_ilike_over_text_filterable_fields():
    session = FakeSession()
    session.on("SELECT * FROM coll_orders", FakeResult(rows=[]))
    collection = make_collection()
    await CollectionRowService(session).search(collection, query="abc")
    sql, params = session.calls[0]
    # title (string) is filterable; notes (text) is not; amount/created are not text
    assert "title ILIKE :query_param" in sql
    assert "query_param" not in sql.replace("title ILIKE :query_param", "")
    assert params["query_param"] == "%abc%"


@pytest.mark.asyncio
async def test_search_filters_build_range_and_ilike_and_eq():
    session = FakeSession()
    session.on("SELECT * FROM coll_orders", FakeResult(rows=[]))
    collection = make_collection()
    filters = {
        "amount": {"from": 1, "to": 9},
        "created": {"from": "2026-01-01"},
        "title": "abc",
        # notes is not filterable: ignored
        "notes": "ignored",
    }
    await CollectionRowService(session).search(collection, filters=filters)
    sql, params = session.calls[0]
    assert "amount >= :p_amount_from" in sql
    assert "amount <= :p_amount_to" in sql
    assert "created >= :p_created_from" in sql
    assert "title ILIKE :p_title" in sql
    assert "notes" not in sql
    assert params["p_amount_from"] == 1
    assert params["p_amount_to"] == 9
    assert params["p_created_from"] == "2026-01-01"
    assert params["p_title"] == "%abc%"


@pytest.mark.asyncio
async def test_search_scalar_numeric_filter_uses_equality():
    session = FakeSession()
    session.on("SELECT * FROM coll_orders", FakeResult(rows=[]))
    collection = make_collection()
    await CollectionRowService(session).search(collection, filters={"amount": 7})
    sql, params = session.calls[0]
    assert "amount = :p_amount" in sql
    assert params["p_amount"] == 7


@pytest.mark.asyncio
async def test_count_returns_scalar_and_uses_where():
    session = FakeSession()
    session.on("SELECT COUNT(*)", FakeResult(scalar=42))
    collection = make_collection()
    assert await CollectionRowService(session).count(collection, filters={"title": "x"}) == 42
    sql, params = session.calls[0]
    assert "SELECT COUNT(*) FROM coll_orders" in sql
    assert "title ILIKE :p_title" in sql
    assert params["p_title"] == "%x%"


# ---------------------------------------------------------------------------
# _resolve_sort
# ---------------------------------------------------------------------------


def test_resolve_sort_default_sort_asc():
    collection = make_collection(default_sort={"field": "title", "order": "asc"})
    assert CollectionRowService._resolve_sort(collection, {"title", "created"}) == ("title", "ASC")


def test_resolve_sort_default_sort_invalid_order_falls_back_to_desc():
    collection = make_collection(default_sort={"field": "title", "order": "sideways"})
    assert CollectionRowService._resolve_sort(collection, {"title"}) == ("title", "DESC")


def test_resolve_sort_default_field_not_sortable_uses_time_column():
    collection = make_collection(
        default_sort={"field": "notes", "order": "asc"},
        time_column="created",
    )
    assert CollectionRowService._resolve_sort(collection, {"title", "created"}) == ("created", "DESC")


def test_resolve_sort_falls_back_to_id():
    collection = make_collection(time_column="notes")
    assert CollectionRowService._resolve_sort(collection, {"title"}) == ("id", "DESC")


# ---------------------------------------------------------------------------
# create_row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_row_empty_payload_rejected():
    collection = make_collection(fields=[])
    with pytest.raises(RowValidationError, match="Row payload is empty"):
        await CollectionRowService(FakeSession()).create_row(collection, {})


@pytest.mark.asyncio
async def test_create_row_unknown_field_rejected():
    collection = make_collection()
    with pytest.raises(RowValidationError, match="Unknown fields: nope"):
        await CollectionRowService(FakeSession()).create_row(collection, {"nope": 1})


@pytest.mark.asyncio
async def test_create_row_coerces_inserts_and_increments_total():
    session = FakeSession()
    session.on("INSERT INTO coll_orders", FakeResult(scalar_one=ROW_ID))
    session.on(
        "SELECT * FROM coll_orders WHERE id = :row_id",
        FakeResult(rows=[{"id": ROW_ID, "title": "abc", "amount": 3}]),
    )
    collection = make_collection()
    row = await CollectionRowService(session).create_row(
        collection, {"title": "abc", "amount": "3"}
    )
    assert row["title"] == "abc"
    insert_sql, insert_params = session.calls[0]
    assert "INSERT INTO coll_orders (title, amount)" in insert_sql
    assert "VALUES (:title, :amount)" in insert_sql
    assert insert_params == {"title": "abc", "amount": 3}
    assert collection.total_rows == 1
    assert session.flush_count >= 1


@pytest.mark.asyncio
async def test_create_row_sql_integrity_error_becomes_validation_error():
    session = FakeSession()
    session.on("SELECT id FROM coll_orders", FakeResult(scalar_one_or_none=None))
    session.on(
        "INSERT INTO coll_orders",
        IntegrityError("insert", {}, Exception("unique")),
    )
    collection = make_collection(
        collection_type=CollectionType.SQL.value,
        fields=[
            {
                "name": "table_name",
                "category": "user",
                "data_type": FieldType.STRING.value,
                "required": False,
                "filterable": True,
                "sortable": False,
            }
        ],
    )
    with pytest.raises(RowValidationError, match="already registered in this SQL collection"):
        await CollectionRowService(session).create_row(collection, {"table_name": "public.t"})


@pytest.mark.asyncio
async def test_create_row_non_sql_integrity_error_reraised():
    session = FakeSession()
    session.on(
        "INSERT INTO coll_orders",
        IntegrityError("insert", {}, Exception("fk")),
    )
    collection = make_collection()
    with pytest.raises(IntegrityError):
        await CollectionRowService(session).create_row(collection, {"title": "x"})


# ---------------------------------------------------------------------------
# update_row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_row_empty_payload_rejected():
    collection = make_collection(fields=[])
    with pytest.raises(RowValidationError, match="Row payload is empty"):
        await CollectionRowService(FakeSession()).update_row(collection, ROW_ID, {})


@pytest.mark.asyncio
async def test_update_row_missing_row_returns_none():
    session = FakeSession()
    session.on("UPDATE coll_orders", FakeResult(rowcount=0))
    collection = make_collection()
    result = await CollectionRowService(session).update_row(collection, ROW_ID, {"title": "x"})
    assert result is None
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_update_row_non_vector_type_skips_vector_reset():
    session = FakeSession()
    session.on("UPDATE coll_orders SET title", FakeResult(rowcount=1))
    session.on(
        "SELECT * FROM coll_orders WHERE id = :row_id",
        FakeResult(rows=[{"id": ROW_ID, "title": "x"}]),
    )
    collection = make_collection()  # no used_in_retrieval fields
    result = await CollectionRowService(session).update_row(collection, ROW_ID, {"title": "x"})
    assert result is not None
    assert not any("_vector_status" in sql for sql, _ in session.calls)
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_update_row_vector_collection_resets_vector_status():
    session = FakeSession()
    session.on("UPDATE coll_orders SET body", FakeResult(rowcount=1))
    session.on(
        "SELECT * FROM coll_orders WHERE id = :row_id",
        FakeResult(rows=[{"id": ROW_ID, "body": "b"}]),
    )
    collection = make_collection(fields=vector_fields())
    await CollectionRowService(session).update_row(collection, ROW_ID, {"body": "b"})
    vector_calls = [c for c in session.calls if "_vector_status = 'pending'" in c[0]]
    assert len(vector_calls) == 1
    assert vector_calls[0][1] == {"row_id": ROW_ID}


@pytest.mark.asyncio
async def test_update_row_skip_vectorization_disables_reset():
    session = FakeSession()
    session.on("UPDATE coll_orders SET body", FakeResult(rowcount=1))
    session.on(
        "SELECT * FROM coll_orders WHERE id = :row_id",
        FakeResult(rows=[{"id": ROW_ID, "body": "b"}]),
    )
    collection = make_collection(fields=vector_fields())
    await CollectionRowService(session).update_row(
        collection, ROW_ID, {"body": "b"}, skip_vectorization=True
    )
    assert not any("_vector_status" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_update_row_sql_integrity_error_becomes_validation_error():
    session = FakeSession()
    session.on("SELECT id FROM coll_orders", FakeResult(scalar_one_or_none=None))
    session.on(
        "UPDATE coll_orders",
        IntegrityError("update", {}, Exception("unique")),
    )
    collection = make_collection(
        collection_type=CollectionType.SQL.value,
        fields=[
            {
                "name": "table_name",
                "category": "user",
                "data_type": FieldType.STRING.value,
                "required": False,
                "filterable": True,
                "sortable": False,
            }
        ],
    )
    with pytest.raises(RowValidationError, match="already registered in this SQL collection"):
        await CollectionRowService(session).update_row(collection, ROW_ID, {"table_name": "t"})


# ---------------------------------------------------------------------------
# insert_rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_rows_empty_list_noop():
    session = FakeSession()
    collection = make_collection()
    assert await CollectionRowService(session).insert_rows(collection, []) == 0
    assert session.calls == []
    assert collection.total_rows == 0


@pytest.mark.asyncio
async def test_insert_rows_bulk_inserts_and_counts():
    session = FakeSession()
    collection = make_collection()
    count = await CollectionRowService(session).insert_rows(
        collection,
        [{"title": "a", "amount": 1}, {"title": "b", "amount": 2, "notes": "n"}],
    )
    assert count == 2
    inserts = [c for c in session.calls if c[0].startswith("INSERT INTO coll_orders")]
    assert len(inserts) == 2
    first_sql, first_params = inserts[0]
    assert "(:title, :amount, :created, :notes)" in first_sql
    assert first_params == {"title": "a", "amount": 1, "created": None, "notes": None}
    assert collection.total_rows == 2


# ---------------------------------------------------------------------------
# delete_rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_rows_empty_list_noop():
    session = FakeSession()
    collection = make_collection()
    assert await CollectionRowService(session).delete_rows(collection, []) == 0
    assert session.calls == []


@pytest.mark.asyncio
async def test_delete_rows_non_vector_collection_skips_qdrant():
    session = FakeSession()
    session.on("DELETE FROM coll_orders", FakeResult(rowcount=2))
    collection = make_collection(collection_type=CollectionType.SQL.value)
    with patch("app.adapters.impl.qdrant.QdrantVectorStore") as store_cls:
        count = await CollectionRowService(session).delete_rows(collection, [ROW_ID, uuid4()])
    assert count == 2
    assert collection.total_rows == 0
    store_cls.assert_not_called()
    assert not any("_vector_status" in sql for sql, _ in session.calls)


@pytest.mark.asyncio
async def test_delete_rows_vector_collection_cleans_qdrant_and_updates_stats():
    session = FakeSession()
    session.on("DELETE FROM coll_orders", FakeResult(rowcount=1))
    session.on(
        "COUNT(*) FILTER",
        FakeResult(rows=[{"vectorized_rows": 3, "failed_rows": 1, "total_chunks": 7}]),
    )
    collection = make_collection(
        fields=vector_fields(),
        qdrant_collection_name="q_orders",
        total_rows=4,
        vector_config={"models": {"m1": {}}},
    )
    store = AsyncMock()
    store.collection_names.return_value = ["vi_extra"]
    store.collection_exists.return_value = True
    delete_by_filter = AsyncMock()
    store.delete_by_filter = delete_by_filter
    with (
        patch("app.adapters.impl.qdrant.QdrantVectorStore", return_value=store),
        patch(
            "app.services.collection.vector_lifecycle.build_model_scoped_qdrant_collections",
            return_value=[("m1", "q_orders__m1")],
        ) as scoped,
        patch(
            "app.services.collection.vector_lifecycle.get_vector_config_model_aliases",
            return_value=["m1"],
        ) as aliases,
    ):
        count = await CollectionRowService(session).delete_rows(collection, [ROW_ID])

    assert count == 1
    assert collection.total_rows == 3
    scoped.assert_called_once_with("q_orders", ["m1"])
    aliases.assert_called_once_with(collection.vector_config)
    called_names = {call.args[0] for call in delete_by_filter.call_args_list}
    assert called_names == {"q_orders", "q_orders__m1", "vi_extra"}
    for call in delete_by_filter.call_args_list:
        assert call.args[1] == {"row_id": [str(ROW_ID)]}
    assert collection.vectorized_rows == 3
    assert collection.failed_rows == 1
    assert collection.total_chunks == 7


@pytest.mark.asyncio
async def test_delete_rows_vector_collection_skips_missing_qdrant_collections():
    session = FakeSession()
    session.on("DELETE FROM coll_orders", FakeResult(rowcount=1))
    session.on(
        "COUNT(*) FILTER",
        FakeResult(rows=[{"vectorized_rows": 0, "failed_rows": 0, "total_chunks": 0}]),
    )
    collection = make_collection(
        fields=vector_fields(), qdrant_collection_name="q_orders", total_rows=1
    )
    store = AsyncMock()
    store.collection_names.return_value = []
    store.collection_exists.return_value = False
    with (
        patch("app.adapters.impl.qdrant.QdrantVectorStore", return_value=store),
        patch(
            "app.services.collection.vector_lifecycle.build_model_scoped_qdrant_collections",
            return_value=[],
        ),
        patch(
            "app.services.collection.vector_lifecycle.get_vector_config_model_aliases",
            return_value=[],
        ),
    ):
        await CollectionRowService(session).delete_rows(collection, [ROW_ID])
    store.delete_by_filter.assert_not_called()


@pytest.mark.asyncio
async def test_delete_rows_without_qdrant_name_skips_vector_cleanup():
    session = FakeSession()
    session.on("DELETE FROM coll_orders", FakeResult(rowcount=1))
    collection = make_collection(fields=vector_fields(), qdrant_collection_name=None)
    with patch("app.adapters.impl.qdrant.QdrantVectorStore") as store_cls:
        await CollectionRowService(session).delete_rows(collection, [ROW_ID])
    store_cls.assert_not_called()
    assert not any("_vector_status" in sql for sql, _ in session.calls)


# ---------------------------------------------------------------------------
# _ensure_sql_table_name_unique
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_table_name_unique_skips_non_sql_collection():
    session = FakeSession()
    collection = make_collection()
    await CollectionRowService(session)._ensure_sql_table_name_unique(
        collection, {"table_name": "t"}
    )
    assert session.calls == []


@pytest.mark.asyncio
async def test_ensure_table_name_unique_skips_payload_without_field():
    session = FakeSession()
    collection = make_collection(collection_type=CollectionType.SQL.value)
    await CollectionRowService(session)._ensure_sql_table_name_unique(collection, {"title": "x"})
    assert session.calls == []


@pytest.mark.asyncio
async def test_ensure_table_name_unique_rejects_blank_value():
    collection = make_collection(collection_type=CollectionType.SQL.value)
    with pytest.raises(RowValidationError, match="Field 'table_name' is required"):
        await CollectionRowService(FakeSession())._ensure_sql_table_name_unique(
            collection, {"table_name": "   "}
        )


@pytest.mark.asyncio
async def test_ensure_table_name_unique_rejects_duplicate():
    session = FakeSession()
    session.on("SELECT id FROM coll_orders", FakeResult(scalar_one_or_none=uuid4()))
    collection = make_collection(collection_type=CollectionType.SQL.value)
    with pytest.raises(RowValidationError, match="already registered"):
        await CollectionRowService(session)._ensure_sql_table_name_unique(
            collection, {"table_name": "dup"}
        )
    sql, params = session.calls[0]
    assert "lower(btrim(table_name)) = lower(btrim(:table_name))" in sql
    assert params == {"table_name": "dup"}


@pytest.mark.asyncio
async def test_ensure_table_name_unique_excludes_self_row_on_update():
    session = FakeSession()
    session.on("SELECT id FROM coll_orders", FakeResult(scalar_one_or_none=None))
    collection = make_collection(collection_type=CollectionType.SQL.value)
    await CollectionRowService(session)._ensure_sql_table_name_unique(
        collection, {"table_name": "t"}, row_id=ROW_ID
    )
    sql, params = session.calls[0]
    assert "AND id <> :row_id" in sql
    assert params == {"table_name": "t", "row_id": ROW_ID}


# ---------------------------------------------------------------------------
# _serialize_row / _build_where
# ---------------------------------------------------------------------------


def test_serialize_row_hides_system_columns():
    collection = make_collection()
    row = {"id": ROW_ID, "title": "t", "_created_at": "x", "_vector_status": "done"}
    assert CollectionRowService._serialize_row(collection, row) == {"id": ROW_ID, "title": "t"}


def test_build_where_empty_returns_true():
    collection = make_collection()
    where_sql, params = CollectionRowService._build_where(collection, {}, None)
    assert where_sql == "TRUE"
    assert params == {}


def test_build_where_no_text_filterable_fields_ignores_query():
    collection = make_collection(
        fields=[
            {
                "name": "amount",
                "category": "user",
                "data_type": FieldType.INTEGER.value,
                "required": False,
                "filterable": True,
                "sortable": False,
            }
        ]
    )
    where_sql, params = CollectionRowService._build_where(collection, {}, "abc")
    assert where_sql == "TRUE"
    assert params == {}


def test_build_where_enum_string_filter_uses_ilike():
    collection = make_collection(
        fields=[
            {
                "name": "state",
                "category": "user",
                "data_type": FieldType.ENUM.value,
                "required": False,
                "filterable": True,
                "sortable": False,
            }
        ]
    )
    where_sql, params = CollectionRowService._build_where(collection, {"state": "open"}, None)
    assert where_sql == "state ILIKE :p_state"
    assert params == {"p_state": "%open%"}


def test_build_where_non_string_value_on_text_field_uses_equality():
    collection = make_collection()
    where_sql, params = CollectionRowService._build_where(
        collection, {"title": {"weird": "dict"}}, None
    )
    assert where_sql == "title = :p_title"
    assert params == {"p_title": {"weird": "dict"}}
