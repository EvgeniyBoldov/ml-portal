"""Unit tests for admin collections core router (app.api.v1.routers.admin.collections_core)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.agents.contracts import CollectionRuntimeStatus
from app.agents.credential_resolver import CredentialsUnavailableError
from app.api.v1.routers.admin import collections_core as core
from app.core.exceptions import InvalidSchemaError
from app.schemas.collections import (
    CreateCollectionRequest,
    FieldSchema,
    SchemaOperation,
    UpdateCollectionRequest,
    VectorConfigSchema,
)
from app.services.collection_service import _UNSET

MODULE = "app.api.v1.routers.admin.collections_core"
TENANT_ID = uuid.uuid4()
COLLECTION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
INSTANCE_ID = uuid.uuid4()
PROVIDER_ID = uuid.uuid4()


def make_admin(tenant_ids=None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), role="admin", tenant_ids=list(tenant_ids or []))


def make_collection(**over) -> SimpleNamespace:
    base = dict(
        id=COLLECTION_ID,
        tenant_id=TENANT_ID,
        slug="orders",
        name="Orders",
        collection_type="table",
        status="active",
        lifecycle_status="active",
        table_schema=None,
        source_contract=None,
        entity_type=None,
        data_instance_id=None,
        is_active=True,
        last_sync_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        current_version=None,
        schema=None,
        data_instance=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def scalar_result(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def row_result(value) -> MagicMock:
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=value)
    return result


def list_result(items) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(items)
    return result


# — Pure helpers: SQL type → JSON schema ——————————————————————————————————————————


class TestJsonSchemaTypeFromSqlType:
    @pytest.mark.parametrize(
        "sql_type,expected",
        [
            ("smallint", ("integer", None)),
            ("integer", ("integer", None)),
            ("BIGINT", ("integer", None)),
            (" numeric ", ("number", None)),
            ("numeric", ("number", None)),
            ("decimal", ("number", None)),
            ("real", ("number", None)),
            ("double precision", ("number", None)),
            ("float", ("number", None)),
            ("money", ("number", None)),
            ("boolean", ("boolean", None)),
            ("json", ("object", None)),
            ("jsonb", ("object", None)),
            ("date", ("string", "date")),
            ("timestamp", ("string", "date-time")),
            ("timestamp with time zone", ("string", "date-time")),
            ("time", ("string", "time")),
            ("time with time zone", ("string", "time")),
            ("character varying(255)", ("string", None)),
            ("uuid", ("string", None)),
            ("", ("string", None)),
            (None, ("string", None)),
        ],
    )
    def test_type_mapping(self, sql_type, expected):
        assert core._json_schema_type_from_sql_type(sql_type) == expected


class TestBuildPostgresDsn:
    def test_explicit_arguments_override_url_parts(self):
        dsn = core._build_postgres_dsn(
            instance_url="postgres://old:old@db.example.com:5433/appdb",
            database_name="warehouse",
            username="svc",
            password="secret",
        )
        assert dsn == "postgresql://svc:secret@db.example.com:5433/warehouse"

    def test_host_only_url_gets_default_port(self):
        dsn = core._build_postgres_dsn(
            instance_url="db.internal",
            database_name="appdb",
            username="u",
            password="p",
        )
        assert dsn == "postgresql://u:p@db.internal:5432/appdb"

    def test_database_user_and_password_fall_back_to_url(self):
        dsn = core._build_postgres_dsn(
            instance_url="postgresql://alice:wonder@host.example/mydb",
            database_name=None,
            username=None,
            password=None,
        )
        assert dsn == "postgresql://alice:wonder@host.example:5432/mydb"

    def test_host_slash_database_form_and_quoting(self):
        dsn = core._build_postgres_dsn(
            instance_url="db.internal/appdb",
            database_name=None,
            username="svc user",
            password="p@ss:word",
        )
        assert dsn == "postgresql://svc%20user:p%40ss%3Aword@db.internal:5432/appdb"

    def test_missing_hostname_is_rejected(self):
        with pytest.raises(ValueError, match="hostname"):
            core._build_postgres_dsn(
                instance_url="", database_name="db", username="u", password="p"
            )

    def test_missing_database_is_rejected(self):
        with pytest.raises(ValueError, match="database_name is required"):
            core._build_postgres_dsn(
                instance_url="db.internal", database_name="  ", username="u", password="p"
            )

    def test_missing_credentials_are_rejected(self):
        with pytest.raises(ValueError, match="username/password are required"):
            core._build_postgres_dsn(
                instance_url="db.internal", database_name="appdb", username=None, password=None
            )


# — Pure helpers: static extraction —————————————————————————————————————————————


class TestExtractRemoteSqlTables:
    def test_table_names_default_to_public_schema(self):
        result = core._extract_remote_sql_tables({"tables": ["beta", "alpha"]}, None)
        assert result == [
            {"schema_name": "public", "table_name": "alpha", "object_type": "BASE TABLE", "table_schema": {}},
            {"schema_name": "public", "table_name": "beta", "object_type": "BASE TABLE", "table_schema": {}},
        ]

    def test_table_dicts_use_name_or_table_and_columns(self):
        result = core._extract_remote_sql_tables(
            {"tables": [{"schema": "sales", "name": "orders", "columns": [{"name": "id"}]}]},
            {"tables": [{"table": "clients"}]},
        )
        assert result == [
            {"schema_name": "public", "table_name": "clients", "object_type": "BASE TABLE", "table_schema": {}},
            {"schema_name": "sales", "table_name": "orders", "object_type": "BASE TABLE", "table_schema": {"columns": [{"name": "id"}]}},
        ]

    def test_columns_must_be_a_list(self):
        result = core._extract_remote_sql_tables({"tables": [{"name": "t", "columns": "nope"}]}, None)
        assert result[0]["table_schema"] == {}

    def test_schemas_list_form(self):
        result = core._extract_remote_sql_tables(
            {"schemas": [{"schema": "s1", "tables": ["t1", {"table": "t2", "columns": []}]}]}, None
        )
        assert [item["table_name"] for item in result] == ["t1", "t2"]
        assert all(item["schema_name"] == "s1" for item in result)

    def test_schemas_dict_form_and_schema_name_fallback(self):
        result = core._extract_remote_sql_tables(
            {"schemas": {"s2": ["t3", {"table": "t5", "columns": [{"name": "c"}]}]}},
            {"schemas": [{"name": "s3", "tables": ["t4"]}]},
        )
        assert [(item["schema_name"], item["table_name"]) for item in result] == [
            ("s2", "t3"),
            ("s2", "t5"),
            ("s3", "t4"),
        ]
        assert result[1]["table_schema"] == {"columns": [{"name": "c"}]}

    def test_duplicates_across_sources_are_deduplicated(self):
        source = {"tables": ["orders"]}
        result = core._extract_remote_sql_tables(source, {"schemas": {"public": ["orders"]}})
        assert len(result) == 1

    def test_invalid_items_are_skipped(self):
        result = core._extract_remote_sql_tables(
            {"tables": ["", "  ", 42, {"name": ""}], "schemas": [{"tables": "not-a-list"}, "nope", 7]},
            "not-a-dict",
        )
        assert result == []

    def test_none_inputs_are_tolerated(self):
        assert core._extract_remote_sql_tables(None, None) == []


class TestNormalizeSqlDiscoverySchema:
    def test_groups_tables_by_schema_with_sorted_output(self):
        discovered = [
            {"schema_name": "public", "table_name": "users", "table_schema": {"properties": {"id": {"type": "integer"}}}},
            {"schema_name": "sales", "table_name": "zz", "table_schema": {"properties": {}}},
            {"schema_name": "sales", "table_name": "aa", "table_schema": {}},
        ]
        result = core._normalize_sql_discovery_schema(discovered)
        assert result == {
            "schemas": [
                {"schema": "public", "tables": [{"name": "users", "table": "users", "columns": [{"name": "id", "data_type": "integer"}]}]},
                {"schema": "sales", "tables": [{"name": "aa", "table": "aa", "columns": []}, {"name": "zz", "table": "zz", "columns": []}]},
            ]
        }

    def test_format_is_used_when_type_is_missing(self):
        result = core._normalize_sql_discovery_schema(
            [{"schema_name": None, "table_name": "t", "table_schema": {"properties": {"when": {"format": "date-time"}}}}]
        )
        table = result["schemas"][0]["tables"][0]
        assert table["columns"] == [{"name": "when", "data_type": "date-time"}]
        assert result["schemas"][0]["schema"] == "public"

    def test_non_dict_specs_and_items_are_skipped(self):
        result = core._normalize_sql_discovery_schema(
            ["nope", {"schema_name": "", "table_name": ""}, {"table_name": "ok", "table_schema": "bad"}]
        )
        assert result == {"schemas": [{"schema": "public", "tables": [{"name": "ok", "table": "ok", "columns": []}]}]}

    def test_empty_discovery_list(self):
        assert core._normalize_sql_discovery_schema([]) == {"schemas": []}


class TestExtractApiEntities:
    def test_string_entities_are_sorted_and_deduplicated(self):
        result = core._extract_api_entities({"entities": ["Zeta", "alpha", "ALPHA", " "]}, None)
        assert [item["entity_type"] for item in result] == ["alpha", "Zeta"]

    def test_dict_entities_normalize_aliases_and_examples(self):
        result = core._extract_api_entities(
            {"entities": [{"name": "Order", "aliases": "invoice", "examples": ["#1", "#1", "", None]}]},
            None,
        )
        assert result == [{"entity_type": "Order", "aliases": ["invoice"], "examples": ["#1"]}]

    def test_entity_type_keys_and_resources(self):
        result = core._extract_api_entities(
            {"entity_types": ["Client"], "resources": [{"resource": "Deal", "aliases": [], "examples": []}]},
            {"entity_types": [42, None]},
        )
        assert [item["entity_type"] for item in result] == ["Client", "Deal"]

    def test_invalid_sources_and_items_are_skipped(self):
        assert core._extract_api_entities({"entities": ["", 1], "resources": ["plain"]}, 5) == []

    def test_none_inputs_are_tolerated(self):
        assert core._extract_api_entities(None, None) == []


# — Connector-based SQL discovery ———————————————————————————————————————————————


def make_data_instance(**over) -> SimpleNamespace:
    base = dict(
        id=INSTANCE_ID,
        access_via_instance_id=PROVIDER_ID,
        url="db.internal/appdb",
        config={"database_name": "warehouse"},
    )
    base.update(over)
    return SimpleNamespace(**base)


def make_provider(**over) -> SimpleNamespace:
    base = dict(connector_type="mcp", url="https://mcp.example/sse", slug="pg-mcp")
    base.update(over)
    return SimpleNamespace(**base)


def connector_rows() -> list:
    return [
        {"table_schema": "public", "table_name": "orders", "column_name": "id", "data_type": "integer", "is_nullable": "NO"},
        {"table_schema": "public", "table_name": "orders", "column_name": "created_at", "data_type": "timestamp with time zone", "is_nullable": "YES"},
        {"table_schema": None, "table_name": "clients", "column_name": "name", "data_type": "character varying", "is_nullable": "YES"},
        "garbage-row",
        {"table_schema": "public", "table_name": "", "column_name": "x"},
        {"table_schema": "public", "table_name": "orphan", "column_name": ""},
    ]


class TestDiscoverSqlTablesViaConnector:
    async def test_missing_data_instance_id_returns_empty(self):
        session = AsyncMock()
        collection = make_collection(collection_type="sql", data_instance_id=None)
        assert await core._discover_sql_tables_via_connector(session, collection) == []
        session.execute.assert_not_awaited()

    async def test_missing_data_instance_row_returns_empty(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=scalar_result(None))
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)
        assert await core._discover_sql_tables_via_connector(session, collection) == []

    async def test_instance_without_provider_returns_empty(self):
        session = AsyncMock()
        instance = make_data_instance(access_via_instance_id=None)
        session.execute = AsyncMock(return_value=scalar_result(instance))
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)
        assert await core._discover_sql_tables_via_connector(session, collection) == []

    async def test_missing_provider_row_returns_empty(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[scalar_result(make_data_instance()), scalar_result(None)])
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)
        assert await core._discover_sql_tables_via_connector(session, collection) == []

    async def test_non_mcp_provider_returns_empty(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[scalar_result(make_data_instance()), scalar_result(make_provider(connector_type="http"))]
        )
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)
        with patch(f"{MODULE}.mcp_initialize", AsyncMock()) as init_mock:
            assert await core._discover_sql_tables_via_connector(session, collection) == []
        init_mock.assert_not_awaited()

    async def test_mcp_provider_without_url_returns_empty(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[scalar_result(make_data_instance()), scalar_result(make_provider(url="   "))]
        )
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)
        assert await core._discover_sql_tables_via_connector(session, collection) == []

    async def test_happy_path_groups_columns_and_builds_dsn(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[scalar_result(make_data_instance()), scalar_result(make_provider(connector_type="MCP"))]
        )
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)

        with patch(f"{MODULE}.mcp_initialize", AsyncMock(return_value="sess-1")) as init_mock, \
                patch(f"{MODULE}.mcp_call_tool", AsyncMock(return_value={"structuredContent": {"rows": connector_rows()}})) as call_mock, \
                patch(f"{MODULE}.mcp_result_error_message", MagicMock(return_value=None)) as error_mock, \
                patch(f"{MODULE}.CredentialService") as cred_cls:
            cred_cls.return_value.resolve_credentials = AsyncMock(
                return_value=SimpleNamespace(payload={"username": "svc", "password": "secret"})
            )
            discovered = await core._discover_sql_tables_via_connector(session, collection)

        init_mock.assert_awaited_once_with(provider_url="https://mcp.example/sse", timeout_s=10)
        cred_cls.return_value.resolve_credentials.assert_awaited_once_with(
            instance_id=INSTANCE_ID, strategy="PLATFORM_FIRST"
        )
        kwargs = call_mock.await_args.kwargs
        assert kwargs["tool_name"] == "execute_sql"
        assert kwargs["session_id"] == "sess-1"
        assert "information_schema.columns" in kwargs["arguments"]["sql"]
        assert kwargs["arguments"]["db_dsn"] == "postgresql://svc:secret@db.internal:5432/warehouse"
        error_mock.assert_called_once()

        assert discovered == [
            {
                "schema_name": "public",
                "table_name": "clients",
                "object_type": "BASE TABLE",
                "table_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
            {
                "schema_name": "public",
                "table_name": "orders",
                "object_type": "BASE TABLE",
                "table_schema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "created_at": {"type": "string", "format": "date-time"},
                    },
                },
            },
        ]

    async def test_dsn_failure_is_tolerated(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                scalar_result(make_data_instance(url="   ", config=None)),
                scalar_result(make_provider()),
            ]
        )
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)

        with patch(f"{MODULE}.mcp_initialize", AsyncMock(return_value="sess-1")), \
                patch(f"{MODULE}.mcp_call_tool", AsyncMock(return_value={"structuredContent": {"rows": []}})) as call_mock, \
                patch(f"{MODULE}.mcp_result_error_message", MagicMock(return_value=None)), \
                patch(f"{MODULE}.CredentialService") as cred_cls:
            cred_cls.return_value.resolve_credentials = AsyncMock(return_value=None)
            discovered = await core._discover_sql_tables_via_connector(session, collection)

        assert discovered == []
        assert "db_dsn" not in call_mock.await_args.kwargs["arguments"]

    async def test_tool_error_raises_invalid_schema_error(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[scalar_result(make_data_instance()), scalar_result(make_provider())]
        )
        collection = make_collection(collection_type="sql", data_instance_id=INSTANCE_ID)

        with patch(f"{MODULE}.mcp_initialize", AsyncMock(return_value="sess-1")), \
                patch(f"{MODULE}.mcp_call_tool", AsyncMock(return_value={"isError": True})), \
                patch(f"{MODULE}.mcp_result_error_message", MagicMock(return_value="connection refused")), \
                patch(f"{MODULE}.CredentialService") as cred_cls:
            cred_cls.return_value.resolve_credentials = AsyncMock(return_value=None)
            with pytest.raises(InvalidSchemaError, match="SQL discovery failed: connection refused"):
                await core._discover_sql_tables_via_connector(session, collection)


# — Endpoints ———————————————————————————————————————————————————————————————————


class TestListAllCollections:
    async def test_builds_paginated_response(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=5)
        session.execute = AsyncMock(return_value=list_result([make_collection(), make_collection()]))
        item = {
            "id": str(COLLECTION_ID),
            "tenant_id": str(TENANT_ID),
            "slug": "orders",
            "name": "Orders",
            "fields": [],
            "status": "active",
            "has_vector_search": False,
            "data_instance_id": str(INSTANCE_ID),
            "is_active": True,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        with patch(f"{MODULE}.CollectionService"), \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value=item)) as build:
            response = await core.list_all_collections(
                page=2, size=2, tenant_id=TENANT_ID, is_active=True,
                include_deprecated=True, search="ord",
                session=session, admin_user=make_admin(),
            )
        assert response.total == 5
        assert response.page == 2
        assert response.size == 2
        assert response.has_more is True
        assert len(response.items) == 2
        assert [parsed.id for parsed in response.items] == [COLLECTION_ID, COLLECTION_ID]
        assert build.await_count == 2

    async def test_missing_total_counts_as_zero(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.execute = AsyncMock(return_value=list_result([]))
        with patch(f"{MODULE}.CollectionService"), \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": "x"})):
            response = await core.list_all_collections(session=session, admin_user=make_admin())
        assert response.total == 0
        assert response.has_more is False
        assert response.items == []


class TestCreateCollection:
    async def test_tenant_id_from_body_wins(self):
        session = AsyncMock()
        collection = make_collection()
        body = CreateCollectionRequest(
            tenant_id=TENANT_ID,
            name="Orders",
            slug="Orders ",
            collection_type="table",
            fields=[FieldSchema(name="Title", data_type="string")],
        )
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": str(COLLECTION_ID)})):
            service = service_cls.return_value
            service.create_collection = AsyncMock(return_value=collection)
            session.execute = AsyncMock(return_value=row_result(collection))
            response = await core.create_collection(
                body=body, session=session, admin_user=make_admin(tenant_ids=[uuid.uuid4()])
            )
        service.create_collection.assert_awaited_once_with(
            tenant_id=TENANT_ID,
            slug="orders",
            name="Orders",
            fields=[body.fields[0].model_dump()],
            source_contract=None,
            vector_config=None,
            collection_type="table",
            data_instance_id=None,
            table_schema=None,
            memory_enabled=False,
        )
        session.commit.assert_awaited_once()
        assert response == {"id": str(COLLECTION_ID)}

    async def test_tenant_id_falls_back_to_first_valid_admin_tenant(self):
        session = AsyncMock()
        collection = make_collection()
        body = CreateCollectionRequest(name="Orders", collection_type="table", vector_config=VectorConfigSchema())
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": "ok"})):
            service = service_cls.return_value
            service.create_collection = AsyncMock(return_value=collection)
            session.execute = AsyncMock(return_value=row_result(collection))
            await core.create_collection(
                body=body, session=session,
                admin_user=make_admin(tenant_ids=["not-a-uuid", str(TENANT_ID)]),
            )
        assert service.create_collection.await_args.kwargs["tenant_id"] == TENANT_ID
        assert service.create_collection.await_args.kwargs["vector_config"] == body.vector_config.model_dump()

    @pytest.mark.parametrize("tenant_ids", [[], ["nope", 12]])
    async def test_without_any_tenant_context_returns_400(self, tenant_ids):
        body = CreateCollectionRequest(name="Orders")
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.create_collection = AsyncMock()
            with pytest.raises(HTTPException) as exc:
                await core.create_collection(
                    body=body, session=AsyncMock(), admin_user=make_admin(tenant_ids=tenant_ids)
                )
        assert exc.value.status_code == 400
        assert "tenant_id" in exc.value.detail


class TestDiscoverSqlTablesEndpoint:
    async def test_unknown_collection_returns_404(self):
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await core.discover_sql_tables(
                    collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
                )
        assert exc.value.status_code == 404

    async def test_non_sql_collection_returns_400(self):
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=make_collection(collection_type="api"))
            with pytest.raises(HTTPException) as exc:
                await core.discover_sql_tables(
                    collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
                )
        assert exc.value.status_code == 400
        assert "only for sql collections" in exc.value.detail

    async def test_static_tables_are_normalized_and_persisted(self):
        session = AsyncMock()
        collection = make_collection(
            collection_type="sql",
            table_schema={"tables": [{"schema": "sales", "name": "orders", "columns": [{"name": "id"}]}]},
            source_contract={"tables": ["clients"]},
        )
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}._discover_sql_tables_via_connector", AsyncMock(side_effect=AssertionError)) as connector:
            service_cls.return_value.get_by_id = AsyncMock(return_value=collection)
            response = await core.discover_sql_tables(
                collection_id=COLLECTION_ID, session=session, admin_user=make_admin()
            )
        connector.assert_not_awaited()
        assert response.total == 2
        assert [item.table_name for item in response.items] == ["clients", "orders"]
        assert collection.table_schema == {
            "schemas": [
                {
                    "schema": "public",
                    "tables": [{"name": "clients", "table": "clients", "columns": []}],
                },
                {
                    # FIXME(known issue): static dict-form columns (table_schema["columns"]) are
                    # dropped on persistence — _normalize_sql_discovery_schema only reads
                    # table_schema["properties"], so the raw "columns" payload is lost.
                    "schema": "sales",
                    "tables": [{"name": "orders", "table": "orders", "columns": []}],
                },
            ]
        }
        assert collection.last_sync_at is not None
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_connector_fallback_is_used_when_nothing_static(self):
        session = AsyncMock()
        collection = make_collection(collection_type="sql", table_schema={}, source_contract={})
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(
                    f"{MODULE}._discover_sql_tables_via_connector",
                    AsyncMock(
                        return_value=[
                            {
                                "schema_name": "public",
                                "table_name": "orders",
                                "object_type": "BASE TABLE",
                                "table_schema": {"type": "object", "properties": {"id": {"type": "integer"}}},
                            }
                        ]
                    ),
                ) as connector:
            service_cls.return_value.get_by_id = AsyncMock(return_value=collection)
            response = await core.discover_sql_tables(
                collection_id=COLLECTION_ID, session=session, admin_user=make_admin()
            )
        connector.assert_awaited_once()
        assert response.total == 1
        assert collection.table_schema == {
            "schemas": [
                {
                    "schema": "public",
                    "tables": [{"name": "orders", "table": "orders", "columns": [{"name": "id", "data_type": "integer"}]}],
                }
            ]
        }

    async def test_connector_without_tables_returns_empty_without_persistence(self):
        session = AsyncMock()
        collection = make_collection(collection_type="sql")
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}._discover_sql_tables_via_connector", AsyncMock(return_value=[])):
            service_cls.return_value.get_by_id = AsyncMock(return_value=collection)
            response = await core.discover_sql_tables(
                collection_id=COLLECTION_ID, session=session, admin_user=make_admin()
            )
        assert response.items == []
        assert response.total == 0
        assert collection.table_schema is None
        session.commit.assert_not_awaited()

    async def test_connector_schema_error_maps_to_400(self):
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(
                    f"{MODULE}._discover_sql_tables_via_connector",
                    AsyncMock(side_effect=InvalidSchemaError("SQL discovery failed: boom")),
                ):
            service_cls.return_value.get_by_id = AsyncMock(return_value=make_collection(collection_type="sql"))
            with pytest.raises(HTTPException) as exc:
                await core.discover_sql_tables(
                    collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
                )
        assert exc.value.status_code == 400
        assert "boom" in exc.value.detail


class TestDiscoverApiEntitiesEndpoint:
    async def test_unknown_collection_returns_404(self):
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await core.discover_api_entities(
                    collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
                )
        assert exc.value.status_code == 404

    async def test_non_api_collection_returns_400(self):
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=make_collection(collection_type="sql"))
            with pytest.raises(HTTPException) as exc:
                await core.discover_api_entities(
                    collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
                )
        assert exc.value.status_code == 400
        assert "only for api collections" in exc.value.detail

    async def test_static_entities_are_extracted(self):
        collection = make_collection(
            collection_type="api",
            table_schema={"entities": ["Deal"]},
            source_contract={"entities": [{"name": "Client", "aliases": "buyer", "examples": ["ACME"]}]},
        )
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=collection)
            response = await core.discover_api_entities(
                collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
            )
        assert response.total == 2
        assert [item.model_dump() for item in response.items] == [
            {"entity_type": "Client", "aliases": ["buyer"], "examples": ["ACME"]},
            {"entity_type": "Deal", "aliases": [], "examples": []},
        ]

    async def test_entity_type_fallback_when_nothing_extracted(self):
        collection = make_collection(collection_type="api", entity_type="Invoice")
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=collection)
            response = await core.discover_api_entities(
                collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
            )
        assert [item.model_dump() for item in response.items] == [
            {"entity_type": "Invoice", "aliases": [], "examples": []}
        ]

    async def test_empty_result_stays_empty(self):
        collection = make_collection(collection_type="api")
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=collection)
            response = await core.discover_api_entities(
                collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
            )
        assert response.items == []
        assert response.total == 0


class TestGetCollectionCapabilities:
    async def _run(self, collection, runtime_cls, cap_cls, snap_cls):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=scalar_result(collection))
        with patch(f"{MODULE}.CollectionRuntimeResolver", runtime_cls), \
                patch(f"{MODULE}.CollectionToolResolver"), \
                patch(f"{MODULE}.CollectionCapabilityResolver", cap_cls), \
                patch("app.services.collection.status_snapshot_service.CollectionStatusSnapshotService", snap_cls):
            return await core.get_collection_capabilities(
                collection_id=COLLECTION_ID, session=session, admin_user=make_admin()
            )

    async def test_unknown_collection_returns_404(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=scalar_result(None))
        with pytest.raises(HTTPException) as exc:
            await core.get_collection_capabilities(
                collection_id=COLLECTION_ID, session=session, admin_user=make_admin()
            )
        assert exc.value.status_code == 404

    async def test_missing_data_instance_returns_no_tools(self):
        runtime_cls = MagicMock()
        runtime_cls.return_value._resolve_collection_source = AsyncMock(return_value=None)
        cap_cls = MagicMock()
        cap_cls.return_value.resolve_for_collection = AsyncMock()
        response = await self._run(make_collection(), runtime_cls, cap_cls, MagicMock())
        assert response == {"collection_id": str(COLLECTION_ID), "collection_slug": "orders", "tools": []}
        cap_cls.return_value.resolve_for_collection.assert_not_awaited()

    async def test_missing_provider_returns_no_tools(self):
        runtime_cls = MagicMock()
        runtime_cls.return_value._resolve_collection_source = AsyncMock(return_value=SimpleNamespace(id=INSTANCE_ID))
        runtime_cls.return_value._resolve_provider_instance = AsyncMock(return_value=None)
        cap_cls = MagicMock()
        cap_cls.return_value.resolve_for_collection = AsyncMock()
        response = await self._run(make_collection(), runtime_cls, cap_cls, MagicMock())
        assert response["tools"] == []
        cap_cls.return_value.resolve_for_collection.assert_not_awaited()

    async def test_full_path_maps_candidates_and_snapshot_status(self):
        collection = make_collection(collection_type="api", slug="crm")
        instance = SimpleNamespace(id=INSTANCE_ID, slug="crm-api")
        provider = SimpleNamespace(id=PROVIDER_ID, slug="hubspot")
        candidate = SimpleNamespace(
            canonical_op_slug="crm.create_client",
            discovered_tool=SimpleNamespace(name="Create client", description="Creates a client"),
            scope_kind="provider",
        )
        runtime_cls = MagicMock()
        runtime_cls.return_value._resolve_collection_source = AsyncMock(return_value=instance)
        runtime_cls.return_value._resolve_provider_instance = AsyncMock(return_value=provider)
        cap_cls = MagicMock()
        cap_cls.return_value.resolve_for_collection = AsyncMock(return_value=[candidate])
        snap_cls = MagicMock()
        snap_cls.return_value.get_status_snapshot = AsyncMock(return_value={"status": "ready"})

        response = await self._run(collection, runtime_cls, cap_cls, snap_cls)

        cap_cls.return_value.resolve_for_collection.assert_awaited_once_with(
            collection=collection, instance=instance, provider=provider
        )
        assert response == {
            "collection_id": str(COLLECTION_ID),
            "collection_slug": "crm",
            "collection_type": "api",
            "status": "ready",
            "tools": [
                {
                    "operation": "crm.create_client",
                    "title": "Create client",
                    "description": "Creates a client",
                    "source": "provider",
                    "provider": "hubspot",
                }
            ],
        }

    async def test_missing_names_fall_back_to_operation_slug_and_collection_status(self):
        collection = make_collection(collection_type="api", status="draft")
        instance = SimpleNamespace(id=INSTANCE_ID)
        provider = SimpleNamespace(id=PROVIDER_ID, slug=None)
        candidate = SimpleNamespace(
            canonical_op_slug="op.x",
            discovered_tool=SimpleNamespace(description=None),
            scope_kind="instance",
        )
        runtime_cls = MagicMock()
        runtime_cls.return_value._resolve_collection_source = AsyncMock(return_value=instance)
        runtime_cls.return_value._resolve_provider_instance = AsyncMock(return_value=provider)
        cap_cls = MagicMock()
        cap_cls.return_value.resolve_for_collection = AsyncMock(return_value=[candidate])
        snap_cls = MagicMock()
        snap_cls.return_value.get_status_snapshot = AsyncMock(return_value={})

        response = await self._run(collection, runtime_cls, cap_cls, snap_cls)

        assert response["status"] == "draft"
        assert response["tools"] == [
            {"operation": "op.x", "title": "op.x", "description": "", "source": "instance", "provider": ""}
        ]


class TestGetAndUpdateAndDelete:
    async def test_get_unknown_collection_returns_404(self):
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await core.get_collection(collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin())
        assert exc.value.status_code == 404

    async def test_get_delegates_to_response_builder(self):
        collection = make_collection()
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": "ok"})) as build:
            service = service_cls.return_value
            service.get_by_id = AsyncMock(return_value=collection)
            response = await core.get_collection(
                collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
            )
        service.get_by_id.assert_awaited_once_with(COLLECTION_ID)
        build.assert_awaited_once_with(service, collection)
        assert response == {"id": "ok"}

    async def test_update_without_memory_flag_does_not_reconcile(self):
        session = AsyncMock()
        collection = make_collection()
        body = UpdateCollectionRequest(name="Updated name")
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": "ok"})), \
                patch("app.workers.tasks_memory.reconcile_collection_memory_policy") as reconcile:
            service = service_cls.return_value
            service.update_collection = AsyncMock(return_value=collection)
            response = await core.update_collection(
                collection_id=COLLECTION_ID, body=body, session=session, admin_user=make_admin()
            )
        kwargs = service.update_collection.await_args.kwargs
        assert kwargs["collection_id"] == COLLECTION_ID
        assert kwargs["name"] == "Updated name"
        for unset_field in ("tenant_id", "is_active", "memory_enabled", "vector_config", "table_name", "table_schema"):
            assert kwargs[unset_field] is _UNSET
        assert kwargs["schema_ops"] == []
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(collection)
        reconcile.delay.assert_not_called()
        assert response == {"id": "ok"}

    async def test_update_memory_flag_schedules_reconciliation(self):
        session = AsyncMock()
        collection = make_collection()
        body = UpdateCollectionRequest(memory_enabled=True)
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": "ok"})), \
                patch("app.workers.tasks_memory.reconcile_collection_memory_policy") as reconcile:
            service_cls.return_value.update_collection = AsyncMock(return_value=collection)
            await core.update_collection(
                collection_id=COLLECTION_ID, body=body, session=session, admin_user=make_admin()
            )
        assert service_cls.return_value.update_collection.await_args.kwargs["memory_enabled"] is True
        reconcile.delay.assert_called_once_with(str(COLLECTION_ID))

    async def test_update_forwards_vector_config_and_schema_ops(self):
        body = UpdateCollectionRequest(
            table_schema={"tables": ["t"]},
            schema_ops=[SchemaOperation(op="remove", name="legacy")],
        )
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": "ok"})), \
                patch("app.workers.tasks_memory.reconcile_collection_memory_policy"):
            service_cls.return_value.update_collection = AsyncMock(return_value=make_collection())
            await core.update_collection(
                collection_id=COLLECTION_ID, body=body, session=AsyncMock(), admin_user=make_admin()
            )
        kwargs = service_cls.return_value.update_collection.await_args.kwargs
        assert kwargs["table_schema"] == {"tables": ["t"]}
        assert kwargs["schema_ops"] == [{"op": "remove", "name": "legacy", "new_name": None, "field": None}]
        assert kwargs["name"] is _UNSET

    async def test_update_vector_config_none_is_forwarded_as_none(self):
        body = UpdateCollectionRequest(vector_config=None)
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}.build_collection_response", AsyncMock(return_value={"id": "ok"})), \
                patch("app.workers.tasks_memory.reconcile_collection_memory_policy"):
            service_cls.return_value.update_collection = AsyncMock(return_value=make_collection())
            await core.update_collection(
                collection_id=COLLECTION_ID, body=body, session=AsyncMock(), admin_user=make_admin()
            )
        assert service_cls.return_value.update_collection.await_args.kwargs["vector_config"] is None

    async def test_delete_unknown_collection_returns_404(self):
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await core.delete_collection(collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin())
        assert exc.value.status_code == 404

    async def test_delete_failure_returns_404(self):
        collection = make_collection()
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service = service_cls.return_value
            service.get_by_id = AsyncMock(return_value=collection)
            service.delete_collection = AsyncMock(return_value=False)
            with pytest.raises(HTTPException) as exc:
                await core.delete_collection(collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin())
        assert exc.value.status_code == 404

    async def test_delete_drops_table_and_commits(self):
        session = AsyncMock()
        collection = make_collection()
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service = service_cls.return_value
            service.get_by_id = AsyncMock(return_value=collection)
            service.delete_collection = AsyncMock(return_value=True)
            response = await core.delete_collection(
                collection_id=COLLECTION_ID, drop_table=False, session=session, admin_user=make_admin()
            )
        service.delete_collection.assert_awaited_once_with("orders", drop_table=False)
        session.commit.assert_awaited_once()
        assert response == {"status": "deleted", "id": str(COLLECTION_ID), "table_dropped": False}


class TestGetCollectionRuntimeReadinessEndpoint:
    async def test_unknown_collection_returns_404(self):
        with patch(f"{MODULE}.CollectionService") as service_cls:
            service_cls.return_value.get_by_id = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc:
                await core.get_collection_runtime_readiness(
                    collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=make_admin()
                )
        assert exc.value.status_code == 404

    async def test_delegates_with_parsed_user_id(self):
        sentinel = object()
        admin = SimpleNamespace(id=str(USER_ID), role="admin", tenant_ids=[])
        with patch(f"{MODULE}.CollectionService") as service_cls, \
                patch(f"{MODULE}._build_collection_runtime_readiness", AsyncMock(return_value=sentinel)) as build:
            service_cls.return_value.get_by_id = AsyncMock(return_value=make_collection())
            response = await core.get_collection_runtime_readiness(
                collection_id=COLLECTION_ID, session=AsyncMock(), admin_user=admin
            )
        assert response is sentinel
        kwargs = build.await_args.kwargs
        assert kwargs["user_id"] == USER_ID
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["collection"].slug == "orders"


# — _build_collection_runtime_readiness —————————————————————————————————————————


def make_runtime_router(**over):
    """Build an OperationRouter stand-in with AsyncMock resolvers."""
    router = MagicMock()
    router.collection_status_snapshot.get_status_snapshot = AsyncMock(return_value={"status": "active"})
    runtime = router.collection_runtime_resolver
    data_instance = over.get("data_instance")
    provider = over.get("provider")
    runtime._resolve_collection_source = AsyncMock(return_value=data_instance)
    runtime._resolve_provider_instance = AsyncMock(return_value=provider)
    # NOTE: real method is a sync @staticmethod; prod calls it without await.
    runtime._resolve_runtime_domain = MagicMock(return_value="remote-sql")
    router.runtime_rbac_resolver.resolve_effective_permissions = AsyncMock(return_value={"allow": True})
    op1, op2 = SimpleNamespace(operation_slug="a.create"), SimpleNamespace(operation_slug="a.list")
    router.operation_resolver.resolve_for_collection = AsyncMock(
        return_value=over.get("operations", [(op1, {"meta": 1}), (op2, {})])
    )
    return router


def readiness_object(missing=None):
    return SimpleNamespace(
        missing_requirements=list(missing or []),
        credential_status="resolved",
        status=CollectionRuntimeStatus.READY,
    )


class TestBuildCollectionRuntimeReadiness:
    async def _run(self, router, readiness):
        builder_cls = MagicMock()
        builder_cls.return_value.build = MagicMock(return_value=readiness)
        settings = SimpleNamespace(COLLECTION_SCHEMA_STALE_HOURS=12)
        with patch(f"{MODULE}.get_settings", MagicMock(return_value=settings)), \
                patch(f"{MODULE}.OperationRouter", MagicMock(return_value=router)), \
                patch(f"{MODULE}.CollectionReadinessBuilder", builder_cls):
            result = await core._build_collection_runtime_readiness(
                session=AsyncMock(),
                collection=make_collection(),
                user_id=USER_ID,
                tenant_id=TENANT_ID,
            )
        return result, builder_cls.return_value.build

    async def test_missing_data_instance_builds_degraded_stub(self):
        router = make_runtime_router(data_instance=None, provider=None)
        readiness = readiness_object()
        result, build = await self._run(router, readiness)
        kwargs = build.call_args.kwargs
        assert result is readiness
        assert kwargs["data_instance"].id is None
        assert kwargs["data_instance"].slug == "missing-data-instance-orders"
        assert kwargs["data_instance"].is_remote is True
        assert kwargs["provider_instance"] is None
        assert kwargs["operations"] == []
        assert kwargs["collection_snapshot"] == {"status": "active"}
        router.operation_resolver.resolve_for_collection.assert_not_awaited()

    async def test_provider_falls_back_to_data_instance(self):
        data_instance = SimpleNamespace(id=INSTANCE_ID, slug="pg", is_remote=True)
        router = make_runtime_router(data_instance=data_instance, provider=None)
        readiness = readiness_object()
        result, build = await self._run(router, readiness)
        kwargs = build.call_args.kwargs
        assert kwargs["provider_instance"] is data_instance
        assert kwargs["data_instance"] is data_instance
        resolved = router.operation_resolver.resolve_for_collection.return_value
        assert kwargs["operations"] == [resolved[0][0], resolved[1][0]]
        assert result is readiness

    async def test_full_path_resolves_operations_with_permissions(self):
        data_instance = SimpleNamespace(id=INSTANCE_ID, slug="pg", is_remote=True)
        provider = SimpleNamespace(id=PROVIDER_ID, slug="pg-mcp", is_remote=True)
        router = make_runtime_router(data_instance=data_instance, provider=provider)
        op1 = router.operation_resolver.resolve_for_collection.return_value[0][0]
        op2 = router.operation_resolver.resolve_for_collection.return_value[1][0]
        readiness = readiness_object()
        result, build = await self._run(router, readiness)

        router.runtime_rbac_resolver.resolve_effective_permissions.assert_awaited_once_with(
            user_id=USER_ID, tenant_id=TENANT_ID, default_collection_allow=True
        )
        router.collection_runtime_resolver._resolve_runtime_domain.assert_called_once()
        resolve_kwargs = router.operation_resolver.resolve_for_collection.await_args.kwargs
        assert resolve_kwargs["runtime_domain"] == "remote-sql"
        assert resolve_kwargs["effective_permissions"] == {"allow": True}
        assert resolve_kwargs["user_id"] == USER_ID
        kwargs = build.call_args.kwargs
        assert kwargs["operations"] == [op1, op2]
        assert result is readiness
        # Operations exist, so the remote-missing-credentials downgrade must not trigger.
        assert readiness.missing_requirements == []
        assert readiness.status == CollectionRuntimeStatus.READY

    async def test_credentials_error_degrades_remote_collection(self):
        data_instance = SimpleNamespace(id=INSTANCE_ID, slug="pg", is_remote=True)
        provider = SimpleNamespace(id=PROVIDER_ID, slug="pg-mcp", is_remote=True)
        router = make_runtime_router(data_instance=data_instance, provider=provider)
        router.operation_resolver.resolve_for_collection = AsyncMock(
            side_effect=CredentialsUnavailableError(
                tool_slug="postgres", operation="execute_sql", scope_required="tenant", reason="no creds"
            )
        )
        readiness = readiness_object()
        result, build = await self._run(router, readiness)
        assert build.call_args.kwargs["operations"] == []
        assert result is readiness
        assert readiness.missing_requirements == ["missing_credentials"]
        assert readiness.credential_status == "missing"
        assert readiness.status == CollectionRuntimeStatus.DEGRADED_MISSING_CREDENTIALS

    async def test_missing_credentials_requirement_is_not_duplicated(self):
        data_instance = SimpleNamespace(id=INSTANCE_ID, slug="pg", is_remote=True)
        provider = SimpleNamespace(id=PROVIDER_ID, slug="pg-mcp", is_remote=True)
        router = make_runtime_router(data_instance=data_instance, provider=provider)
        router.operation_resolver.resolve_for_collection = AsyncMock(return_value=[])
        readiness = readiness_object(missing=["missing_credentials"])
        await self._run(router, readiness)
        assert readiness.missing_requirements == ["missing_credentials"]
        assert readiness.credential_status == "missing"
        assert readiness.status == CollectionRuntimeStatus.DEGRADED_MISSING_CREDENTIALS

    async def test_local_collection_with_no_operations_is_not_degraded(self):
        data_instance = SimpleNamespace(id=INSTANCE_ID, slug="local", is_remote=False)
        router = make_runtime_router(data_instance=data_instance, provider=data_instance)
        router.operation_resolver.resolve_for_collection = AsyncMock(return_value=[])
        readiness = readiness_object()
        result, build = await self._run(router, readiness)
        assert build.call_args.kwargs["operations"] == []
        assert result is readiness
        assert readiness.missing_requirements == []
        assert readiness.credential_status == "resolved"
        assert readiness.status == CollectionRuntimeStatus.READY

    async def test_builder_receives_schema_staleness_setting(self):
        router = make_runtime_router(data_instance=None, provider=None)
        with patch(f"{MODULE}.get_settings", MagicMock(return_value=SimpleNamespace(COLLECTION_SCHEMA_STALE_HOURS=48))), \
                patch(f"{MODULE}.OperationRouter", MagicMock(return_value=router)), \
                patch(f"{MODULE}.CollectionReadinessBuilder") as builder_cls:
            builder_cls.return_value.build = MagicMock(return_value=readiness_object())
            await core._build_collection_runtime_readiness(
                session=AsyncMock(), collection=make_collection(), user_id=USER_ID, tenant_id=TENANT_ID
            )
        builder_cls.assert_called_once_with(schema_stale_after_hours=48)
