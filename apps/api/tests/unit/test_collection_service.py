"""Unit tests for the CollectionService facade.

The facade is constructed with a recording fake session; sub-services are
replaced with AsyncMock after construction. Covers update_collection guards
and merging, create_collection memory gating, SQL storage bootstrapping,
contract alignment, template row deletion wiring, artifact cleanup and
delegation contracts (including the _UNSET sentinel).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import (
    CollectionNotFoundError,
    ConflictError,
    ValidationError as DomainValidationError,
)
from app.models.collection import Collection, CollectionType, FieldType
from app.services.collection_service import CollectionService, _UNSET

TENANT_ID = uuid4()
COLLECTION_ID = uuid4()
INSTANCE_ID = uuid4()
ROW_IDS = [uuid4(), uuid4()]


class RecordingSession:
    """Fake AsyncSession recording executed statements."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.added: list = []
        self.flush_count = 0
        self.refreshed: list[tuple] = []
        self.fail_on: str | None = None

    async def execute(self, stmt, params: dict | None = None):
        sql = " ".join(str(stmt).split())
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("boom")
        self.executed.append(sql)
        return []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, obj, attribute_names=None):
        self.refreshed.append((obj, attribute_names))


def make_collection(**overrides: Any) -> Collection:
    base: dict[str, Any] = dict(
        tenant_id=TENANT_ID,
        slug="orders",
        name="Orders",
        collection_type=CollectionType.TABLE.value,
        data_instance_id=INSTANCE_ID,
        table_name="coll_orders",
        total_rows=0,
        status="ready",
        is_active=True,
        memory_enabled=False,
        vector_config=None,
        qdrant_collection_name=None,
    )
    base.update(overrides)
    collection = Collection(**base)
    collection.fields = overrides.get(
        "fields",
        [
            {
                "name": "title",
                "category": "user",
                "data_type": FieldType.STRING.value,
                "required": False,
                "filterable": True,
                "sortable": True,
            }
        ],
    )
    return collection


def make_service(session: RecordingSession | None = None) -> tuple[CollectionService, RecordingSession]:
    session = session or RecordingSession()
    svc = CollectionService(session)
    svc.query = AsyncMock()
    svc.rows = AsyncMock()
    svc.versions = AsyncMock()
    svc.schema_evolution = AsyncMock()
    svc.lifecycle = AsyncMock()
    svc.status_snapshot = AsyncMock()
    svc.status_snapshot.sync_collection_status.return_value = {"status": "ready"}
    svc.vector = MagicMock()
    svc.contract = MagicMock()
    return svc, session


# ---------------------------------------------------------------------------
# create_collection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_collection_rejects_memory_for_non_document():
    svc, _ = make_service()
    with pytest.raises(DomainValidationError, match="memory_enabled is only supported"):
        await svc.create_collection(
            TENANT_ID, "orders", "Orders", fields=[], memory_enabled=True
        )
    svc.lifecycle.create_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_collection_delegates_and_sets_memory_flag():
    svc, session = make_service()
    created = make_collection(collection_type=CollectionType.DOCUMENT.value)
    svc.lifecycle.create_collection.return_value = created
    result = await svc.create_collection(
        TENANT_ID,
        "docs",
        "Docs",
        fields=[{"name": "title"}],
        collection_type=CollectionType.DOCUMENT.value,
        memory_enabled=True,
        vector_config={"models": {}},
    )
    assert result.memory_enabled is True
    svc.lifecycle.create_collection.assert_awaited_once_with(
        tenant_id=TENANT_ID,
        slug="docs",
        name="Docs",
        fields=[{"name": "title"}],
        source_contract=None,
        vector_config={"models": {}},
        collection_type=CollectionType.DOCUMENT.value,
        data_instance_id=None,
        table_name=None,
        table_schema=None,
    )
    assert session.flush_count == 1


# ---------------------------------------------------------------------------
# update_collection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_collection_missing_raises():
    svc, _ = make_service()
    svc.query.get_by_id.return_value = None
    with pytest.raises(CollectionNotFoundError):
        await svc.update_collection(COLLECTION_ID, name="x")


@pytest.mark.asyncio
async def test_update_collection_rejects_deprecated():
    svc, _ = make_service()
    collection = make_collection()
    collection.lifecycle_status = "deprecated"
    svc.query.get_by_id.return_value = collection
    with pytest.raises(ConflictError, match="deprecated"):
        await svc.update_collection(COLLECTION_ID, name="x")


@pytest.mark.asyncio
async def test_update_collection_rejects_memory_for_non_document():
    svc, _ = make_service()
    svc.query.get_by_id.return_value = make_collection()
    with pytest.raises(DomainValidationError, match="memory_enabled is only supported"):
        await svc.update_collection(COLLECTION_ID, memory_enabled=True)


@pytest.mark.asyncio
async def test_update_collection_rejects_data_instance_change():
    svc, _ = make_service()
    svc.query.get_by_id.return_value = make_collection()
    with pytest.raises(ConflictError, match="create a new collection instead"):
        await svc.update_collection(COLLECTION_ID, data_instance_id=uuid4())


@pytest.mark.asyncio
async def test_update_collection_reassigns_tenant_when_changed():
    svc, _ = make_service()
    svc.query.get_by_id.return_value = make_collection()
    svc._reassign_collection_tenant = AsyncMock()
    new_tenant = uuid4()
    await svc.update_collection(COLLECTION_ID, tenant_id=new_tenant)
    svc._reassign_collection_tenant.assert_awaited_once_with(
        svc.query.get_by_id.return_value, new_tenant
    )


@pytest.mark.asyncio
async def test_update_collection_same_tenant_skips_reassign():
    svc, _ = make_service()
    svc.query.get_by_id.return_value = make_collection()
    svc._reassign_collection_tenant = AsyncMock()
    await svc.update_collection(COLLECTION_ID, tenant_id=TENANT_ID)
    svc._reassign_collection_tenant.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_collection_applies_fields_and_flushes():
    svc, session = make_service()
    collection = make_collection(
        vector_config={"chunk_strategy": "by_paragraphs", "keep": 1}
    )
    svc.query.get_by_id.return_value = collection
    result = await svc.update_collection(
        COLLECTION_ID,
        name="New name",
        is_active=False,
        memory_enabled=False,
        vector_config={"chunk_size": 9},
        table_name="coll_new",
        table_schema={"cols": []},
        data_instance_id=INSTANCE_ID,
    )
    assert result is collection
    assert collection.name == "New name"
    assert collection.is_active is False
    assert collection.memory_enabled is False
    assert collection.vector_config == {
        "chunk_strategy": "by_paragraphs",
        "keep": 1,
        "chunk_size": 9,
    }
    assert collection.table_name == "coll_new"
    assert collection.table_schema == {"cols": []}
    svc.schema_evolution.apply_schema_operations.assert_not_awaited()
    svc.status_snapshot.sync_collection_status.assert_awaited_once_with(
        collection, persist=False
    )
    assert session.added == [collection]
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_update_collection_applies_schema_ops():
    svc, _ = make_service()
    collection = make_collection()
    svc.query.get_by_id.return_value = collection
    svc.schema_evolution = AsyncMock()
    await svc.update_collection(COLLECTION_ID, schema_ops=[{"op": "add"}])
    svc.schema_evolution.apply_schema_operations.assert_awaited_once_with(
        collection, [{"op": "add"}]
    )


@pytest.mark.asyncio
async def test_update_collection_clears_vector_config_with_none():
    svc, _ = make_service()
    collection = make_collection(vector_config={"chunk_size": 5})
    svc.query.get_by_id.return_value = collection
    await svc.update_collection(COLLECTION_ID, vector_config=None)
    assert collection.vector_config is None


# ---------------------------------------------------------------------------
# _generate_table_name
# ---------------------------------------------------------------------------


def test_generate_table_name_uses_tenant_prefix_and_slug():
    svc, _ = make_service()
    tenant = uuid4()
    expected = f"coll_{str(tenant).replace('-', '')[:8]}_orders"
    assert svc._generate_table_name(tenant, "orders") == expected


# ---------------------------------------------------------------------------
# ensure_sql_storage_table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_sql_storage_table_ignores_table_collections():
    svc, session = make_service()
    collection = make_collection()
    await svc.ensure_sql_storage_table(collection)
    assert session.executed == []
    assert session.added == []


@pytest.mark.asyncio
async def test_ensure_sql_storage_table_api_type_with_table_skips_flush():
    svc, session = make_service()
    collection = make_collection(
        collection_type=CollectionType.API.value,
        fields=[{"name": "title", "category": "user", "data_type": "string"}],
    )
    await svc.ensure_sql_storage_table(collection)
    joined = "\n".join(session.executed)
    assert "CREATE TABLE IF NOT EXISTS coll_orders" in joined
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in joined
    assert "table_name_uniq" not in joined  # SQL-only index
    assert session.added == []  # nothing changed
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_ensure_sql_storage_table_generates_table_and_unique_index():
    svc, session = make_service()
    preset = [
        {
            "name": "table_name",
            "category": "specific",
            "data_type": FieldType.STRING.value,
            "required": False,
        }
    ]
    svc.contract.ensure_sql_preset_fields.return_value = preset
    collection = make_collection(
        collection_type=CollectionType.SQL.value, table_name=None, fields=[]
    )
    collection.fields = []
    await svc.ensure_sql_storage_table(collection)
    expected_table = f"coll_{str(TENANT_ID).replace('-', '')[:8]}_orders"
    assert collection.table_name == expected_table
    joined = "\n".join(session.executed)
    assert f"CREATE TABLE IF NOT EXISTS {expected_table}" in joined
    assert (
        f"ALTER TABLE {expected_table} ADD COLUMN IF NOT EXISTS table_name VARCHAR(255)"
        in joined
    )
    assert (
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{expected_table}_table_name_uniq "
        f"ON {expected_table} (lower(btrim(table_name))) WHERE table_name IS NOT NULL"
    ) in joined
    svc.contract.ensure_sql_preset_fields.assert_called_once_with([])
    assert session.added == [collection]
    assert session.flush_count == 1


# ---------------------------------------------------------------------------
# ensure_contract_fields_present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "collection_type",
    [CollectionType.API.value],
)
async def test_ensure_contract_fields_present_early_exit_for_remote(collection_type):
    svc, session = make_service()
    collection = make_collection(collection_type=collection_type)
    result = await svc.ensure_contract_fields_present(collection)
    assert result is collection
    assert session.executed == []


@pytest.mark.asyncio
async def test_ensure_contract_fields_present_early_exit_without_table():
    svc, session = make_service()
    collection = make_collection(collection_type=CollectionType.DOCUMENT.value, table_name=None)
    result = await svc.ensure_contract_fields_present(collection)
    assert result is collection
    assert session.executed == []


@pytest.mark.asyncio
async def test_ensure_contract_fields_present_early_exit_for_table_type():
    svc, session = make_service()
    collection = make_collection(collection_type=CollectionType.TABLE.value)
    result = await svc.ensure_contract_fields_present(collection)
    assert result is collection
    assert session.executed == []


@pytest.mark.asyncio
async def test_ensure_contract_fields_present_adds_missing_and_tightens_nullability():
    svc, session = make_service()
    current = [
        {"name": "title", "category": "user", "data_type": "string", "required": False},
        {"name": "body", "category": "user", "data_type": "text", "required": False},
    ]
    expected = [
        {"name": "status", "category": "specific", "data_type": "enum", "required": False},
        {"name": "title", "category": "user", "data_type": "string", "required": True},
        {"name": "body", "category": "user", "data_type": "text", "required": False},
    ]
    svc.contract.ensure_document_preset_fields.return_value = expected
    svc.vector.fields_require_table_vector_search.return_value = False
    svc.vector.count_nulls = AsyncMock(return_value=0)
    collection = make_collection(
        collection_type=CollectionType.DOCUMENT.value, fields=current
    )
    svc._get_table_column_nullability = AsyncMock(return_value={})
    await svc.ensure_contract_fields_present(collection)
    joined = "\n".join(session.executed)
    assert (
        "ALTER TABLE coll_orders ADD COLUMN IF NOT EXISTS status VARCHAR(100) "
        "DEFAULT 'uploaded'" in joined
    )
    assert "ALTER TABLE coll_orders ALTER COLUMN title SET NOT NULL" in joined
    assert "DROP NOT NULL" not in joined
    svc.vector.count_nulls.assert_awaited_once_with("coll_orders", "title")
    assert collection.fields == expected
    svc.contract.normalize_default_sort.assert_called_once_with(collection, expected)
    assert session.flush_count == 1
    assert session.refreshed and session.refreshed[0][0] is collection


@pytest.mark.asyncio
async def test_ensure_contract_fields_present_loosens_nullability():
    svc, session = make_service()
    current = [
        {"name": "title", "category": "user", "data_type": "string", "required": True},
    ]
    expected = [
        {"name": "title", "category": "user", "data_type": "string", "required": False},
    ]
    svc.contract.ensure_document_preset_fields.return_value = expected
    svc.vector.fields_require_table_vector_search.return_value = False
    collection = make_collection(
        collection_type=CollectionType.DOCUMENT.value, fields=current
    )
    svc._get_table_column_nullability = AsyncMock(return_value={})
    await svc.ensure_contract_fields_present(collection)
    assert "ALTER TABLE coll_orders ALTER COLUMN title DROP NOT NULL" in "\n".join(
        session.executed
    )


@pytest.mark.asyncio
async def test_ensure_contract_fields_present_provisions_vector_infra():
    svc, session = make_service()
    expected = [
        {"name": "title", "category": "user", "data_type": "string", "required": False},
    ]
    svc.contract.ensure_document_preset_fields.return_value = expected
    svc.vector.fields_require_table_vector_search.return_value = True
    svc.vector.ensure_table_vector_infra = AsyncMock()
    svc.vector.provision_qdrant_collection = AsyncMock()
    collection = make_collection(
        collection_type=CollectionType.DOCUMENT.value, fields=list(expected)
    )
    svc._get_table_column_nullability = AsyncMock(return_value={})
    await svc.ensure_contract_fields_present(collection, ensure_vector_infra=True)
    assert collection.vector_config == {
        "chunk_strategy": "by_paragraphs",
        "chunk_size": 512,
        "overlap": 50,
    }
    assert collection.qdrant_collection_name == "coll_orders"
    svc.vector.ensure_table_vector_infra.assert_awaited_once_with(collection)
    svc.vector.provision_qdrant_collection.assert_awaited_once_with(
        TENANT_ID, "coll_orders"
    )


# ---------------------------------------------------------------------------
# delete_rows (facade)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_rows_template_cleans_analysis_nodes():
    svc, _ = make_service()
    collection = make_collection(collection_type=CollectionType.TEMPLATE.value)
    svc.rows.delete_rows.return_value = 2
    with patch(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository"
    ) as repo_cls:
        repo_cls.return_value.delete_nodes_by_row_id = AsyncMock()
        count = await svc.delete_rows(collection, ROW_IDS)
    assert count == 2
    repo_cls.assert_called_once_with(svc.session)
    awaited = repo_cls.return_value.delete_nodes_by_row_id.await_args_list
    assert [(c.args[0], c.args[1]) for c in awaited] == [
        (collection.id, ROW_IDS[0]),
        (collection.id, ROW_IDS[1]),
    ]
    svc.status_snapshot.sync_collection_status.assert_awaited_once_with(
        collection, persist=False
    )


@pytest.mark.asyncio
async def test_delete_rows_non_template_skips_analysis_repo():
    svc, _ = make_service()
    collection = make_collection()
    svc.rows.delete_rows.return_value = 1
    with patch(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository"
    ) as repo_cls:
        await svc.delete_rows(collection, ROW_IDS)
    repo_cls.assert_not_called()


@pytest.mark.asyncio
async def test_delete_rows_zero_count_still_syncs_status():
    svc, _ = make_service()
    collection = make_collection(collection_type=CollectionType.TEMPLATE.value)
    svc.rows.delete_rows.return_value = 0
    with patch(
        "app.repositories.template_analysis_status_repo.AsyncTemplateAnalysisStatusRepository"
    ) as repo_cls:
        count = await svc.delete_rows(collection, ROW_IDS)
    assert count == 0
    repo_cls.assert_not_called()
    svc.status_snapshot.sync_collection_status.assert_awaited_once()


# ---------------------------------------------------------------------------
# Row/query delegation wrappers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_rows_and_create_row_sync_status():
    svc, _ = make_service()
    collection = make_collection()
    svc.rows.insert_rows.return_value = 3
    svc.rows.create_row.return_value = {"id": 1}
    assert await svc.insert_rows(collection, [{"a": 1}]) == 3
    assert await svc.create_row(collection, {"a": 1}) == {"id": 1}
    assert svc.status_snapshot.sync_collection_status.await_count == 2


@pytest.mark.asyncio
async def test_update_row_syncs_status_only_when_row_updated():
    svc, _ = make_service()
    collection = make_collection()
    svc.rows.update_row.return_value = None
    assert await svc.update_row(collection, ROW_IDS[0], {"title": "x"}) is None
    svc.status_snapshot.sync_collection_status.assert_not_awaited()
    svc.rows.update_row.return_value = {"id": ROW_IDS[0]}
    assert await svc.update_row(collection, ROW_IDS[0], {"title": "x"}) == {
        "id": ROW_IDS[0]
    }
    svc.status_snapshot.sync_collection_status.assert_awaited_once_with(
        collection, persist=False
    )


@pytest.mark.asyncio
async def test_search_and_count_pass_arguments_through():
    svc, _ = make_service()
    collection = make_collection()
    svc.rows.search.return_value = [{"id": 1}]
    svc.rows.count.return_value = 7
    assert await svc.search(collection, filters={"a": 1}, limit=5, offset=2, query="q") == [
        {"id": 1}
    ]
    assert await svc.count(collection, filters={"a": 1}, query="q") == 7
    svc.rows.search.assert_awaited_once_with(
        collection, filters={"a": 1}, limit=5, offset=2, query="q"
    )
    svc.rows.count.assert_awaited_once_with(collection, filters={"a": 1}, query="q")


@pytest.mark.asyncio
async def test_query_delegation():
    svc, _ = make_service()
    await svc.get_by_id(COLLECTION_ID)
    await svc.get_by_slug("orders", include_inactive=True)
    await svc.list_collections(TENANT_ID, active_only=False)
    await svc.update_row_count(COLLECTION_ID)
    await svc.get_effective_total_rows(make_collection())
    await svc.get_status_snapshot(make_collection())
    svc.query.get_by_id.assert_awaited_once_with(COLLECTION_ID)
    svc.query.get_by_slug.assert_awaited_once_with("orders", include_inactive=True)
    svc.query.list_collections.assert_awaited_once_with(TENANT_ID, active_only=False)
    svc.query.update_row_count.assert_awaited_once_with(COLLECTION_ID)


@pytest.mark.asyncio
async def test_version_delegation_passes_unset_sentinel():
    svc, _ = make_service()
    await svc.update_version(COLLECTION_ID, 2, notes="n")
    call = svc.versions.update_version.await_args
    assert call.args[0] == COLLECTION_ID
    assert call.args[1] == 2
    assert call.kwargs["notes"] == "n"
    assert call.kwargs["data_description"] is _UNSET
    assert call.kwargs["_UNSET"] is _UNSET


@pytest.mark.asyncio
async def test_delete_collection_delegates():
    svc, _ = make_service()
    svc.lifecycle.delete_collection.return_value = True
    assert await svc.delete_collection("orders", drop_table=False) is True
    svc.lifecycle.delete_collection.assert_awaited_once_with("orders", drop_table=False)


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_collection_artifacts_drops_table_and_qdrant():
    svc, session = make_service()
    svc.vector.cleanup_qdrant_collection = AsyncMock()
    await svc._cleanup_collection_creation_artifacts(
        table_name="coll_x", qdrant_collection_name="q_x"
    )
    assert any("DROP TABLE IF EXISTS coll_x CASCADE" in sql for sql in session.executed)
    svc.vector.cleanup_qdrant_collection.assert_awaited_once_with("q_x")


@pytest.mark.asyncio
async def test_cleanup_collection_artifacts_swallows_drop_failure():
    svc, session = make_service()
    session.fail_on = "DROP TABLE"
    svc.vector.cleanup_qdrant_collection = AsyncMock()
    await svc._cleanup_collection_creation_artifacts(
        table_name="coll_x", qdrant_collection_name=None
    )
    svc.vector.cleanup_qdrant_collection.assert_awaited_once_with("")


# ---------------------------------------------------------------------------
# Index rebuild & nullability introspection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_structural_indexes_drops_then_creates():
    svc, session = make_service()
    with (
        patch(
            "app.services.collection_service._build_drop_indexes_sql",
            return_value=["DROP INDEX old"],
        ) as drop_builder,
        patch(
            "app.services.collection_service._build_indexes_sql",
            return_value=["CREATE INDEX new"],
        ) as create_builder,
    ):
        await svc._rebuild_structural_indexes(
            "coll_orders",
            [{"name": "gone"}, {"name": "kept"}],
            [{"name": "kept"}, {"name": "fresh"}],
        )
    assert drop_builder.call_count == 3  # union of touched names
    touched = {c.args[1] for c in drop_builder.call_args_list}
    assert touched == {"gone", "kept", "fresh"}
    create_builder.assert_called_once_with("coll_orders", [{"name": "kept"}, {"name": "fresh"}])
    assert session.executed.count("DROP INDEX old") == 3
    assert session.executed.count("CREATE INDEX new") == 1
    assert session.executed.index("CREATE INDEX new") > session.executed.index("DROP INDEX old")


@pytest.mark.asyncio
async def test_get_table_column_nullability_maps_rows():
    svc, session = make_service()

    async def fake_execute(stmt, params=None):
        return [
            SimpleNamespace(column_name="title", is_nullable="YES"),
            SimpleNamespace(column_name="amount", is_nullable="NO"),
        ]

    session.execute = fake_execute  # type: ignore[method-assign]
    result = await svc._get_table_column_nullability("coll_orders")
    assert result == {"title": True, "amount": False}
