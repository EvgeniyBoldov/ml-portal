from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidSchemaError
from app.models.collection import Collection, CollectionType
from app.models.tool_instance import ToolInstance
from app.services.credential_service import CredentialService
from app.services.mcp_jsonrpc_client import mcp_call_tool, mcp_initialize, mcp_result_error_message


@dataclass
class CollectionDiscoveryResult:
    kind: str
    items: list[dict[str, Any]]


class BaseCollectionTypeProfile(ABC):
    collection_type: str

    def ensure_specific_fields(self, contract, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(fields)

    def expected_data_connector_subtype(self) -> Optional[str]:
        return None

    def supports_discovery(self) -> bool:
        return False

    async def discover(
        self,
        *,
        collection: Collection,
        session: AsyncSession,
        admin_user: Any,
    ) -> CollectionDiscoveryResult:
        raise InvalidSchemaError(f"Discovery is not supported for '{self.collection_type}' collections")


class TableCollectionTypeProfile(BaseCollectionTypeProfile):
    collection_type = CollectionType.TABLE.value


class DocumentCollectionTypeProfile(BaseCollectionTypeProfile):
    collection_type = CollectionType.DOCUMENT.value

    def ensure_specific_fields(self, contract, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return contract.ensure_document_preset_fields(fields)


class SqlCollectionTypeProfile(BaseCollectionTypeProfile):
    collection_type = CollectionType.SQL.value

    def ensure_specific_fields(self, contract, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return contract.ensure_sql_preset_fields(fields)

    def expected_data_connector_subtype(self) -> Optional[str]:
        return "sql"

    def supports_discovery(self) -> bool:
        return True

    async def discover(
        self,
        *,
        collection: Collection,
        session: AsyncSession,
        admin_user: Any,
    ) -> CollectionDiscoveryResult:
        if not collection.data_instance_id:
            raise InvalidSchemaError("SQL collection is not bound to data instance")

        result = await session.execute(
            select(ToolInstance).where(ToolInstance.id == collection.data_instance_id)
        )
        sql_instance = result.scalar_one_or_none()
        if not sql_instance:
            raise InvalidSchemaError("Data instance not found")
        if str(sql_instance.connector_subtype or "").strip().lower() != "sql":
            raise InvalidSchemaError(
                "Collection is bound to non-SQL instance. "
                "Bind collection to a data connector with connector_subtype=sql."
            )
        if not sql_instance.access_via_instance_id:
            raise InvalidSchemaError("SQL connector has no linked MCP provider (access_via_instance_id)")

        provider_result = await session.execute(
            select(ToolInstance).where(ToolInstance.id == sql_instance.access_via_instance_id)
        )
        provider = provider_result.scalar_one_or_none()
        if not provider:
            raise InvalidSchemaError("Linked MCP provider not found")
        if str(provider.connector_type or "").strip().lower() != "mcp" or not str(provider.url or "").strip():
            raise InvalidSchemaError("Linked provider is not a valid MCP connector")

        config = sql_instance.config or {}
        cred_service = CredentialService(session)
        decrypted = await cred_service.resolve_credentials(
            instance_id=sql_instance.id,
            strategy="ANY",
            user_id=_coerce_user_uuid(getattr(admin_user, "id", None)),
            tenant_id=collection.tenant_id,
        )
        payload = (decrypted.payload or {}) if decrypted else {}
        schema_name = str(config.get("schema_name") or "").strip() or None
        optional_args: dict[str, str] = {}
        try:
            dsn = _build_postgres_dsn(
                instance_url=sql_instance.url,
                database_name=str(config.get("database_name") or "").strip() or None,
                username=payload.get("username"),
                password=payload.get("password"),
            )
            optional_args["db_dsn"] = dsn
        except ValueError:
            # Provider may already be configured with DB_DSN.
            pass

        try:
            session_id = await mcp_initialize(provider_url=provider.url, timeout_s=20)
            search_result = await mcp_call_tool(
                provider_url=provider.url,
                session_id=session_id,
                tool_name="search_objects",
                arguments={
                    "query": "",
                    "schema": schema_name,
                    "object_types": ["table", "view"],
                    "limit": 500,
                    **optional_args,
                },
                timeout_s=30,
            )
        except Exception as exc:
            raise InvalidSchemaError(f"SQL discovery failed (MCP): {exc}") from exc

        search_error = mcp_result_error_message(search_result)
        if search_error:
            raise InvalidSchemaError(f"SQL discovery failed (search_objects): {search_error}")

        raw_items = (search_result.get("structuredContent") or {}).get("items") or []
        table_pairs: list[tuple[str, str, str]] = []
        seen_pairs: set[tuple[str, str, str]] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            object_name = str(item.get("object_name") or "").strip()
            schema = str(item.get("schema_name") or "").strip()
            object_type = str(item.get("object_type") or "").strip().upper()
            if not object_name or not schema:
                continue
            if object_type and object_type not in {"BASE TABLE", "VIEW"}:
                continue
            key = (schema, object_name, object_type or "BASE TABLE")
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            table_pairs.append(key)

        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for schema, table, object_type in table_pairs:
            columns_sql = (
                "SELECT column_name, is_nullable, data_type, udt_name "
                "FROM information_schema.columns "
                f"WHERE table_schema = {_sql_literal(schema)} "
                f"AND table_name = {_sql_literal(table)} "
                "ORDER BY ordinal_position"
            )
            try:
                columns_result = await mcp_call_tool(
                    provider_url=provider.url,
                    session_id=session_id,
                    tool_name="execute_sql",
                    arguments={"sql": columns_sql, **optional_args},
                    timeout_s=30,
                )
            except Exception as exc:
                raise InvalidSchemaError(
                    f"SQL discovery failed while reading columns for {schema}.{table}: {exc}"
                ) from exc

            columns_error = mcp_result_error_message(columns_result)
            if columns_error:
                raise InvalidSchemaError(
                    f"SQL discovery failed while reading columns for {schema}.{table}: {columns_error}"
                )

            rows = (columns_result.get("structuredContent") or {}).get("rows") or []
            item = {
                "schema_name": schema,
                "table_name": table,
                "object_type": object_type,
                "table_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": True,
                },
            }
            for row in rows:
                if not isinstance(row, dict):
                    continue
                column_name = str(row.get("column_name") or "").strip()
                if not column_name:
                    continue
                item["table_schema"]["properties"][column_name] = _json_type_for_pg(
                    str(row.get("data_type") or ""),
                    row.get("udt_name"),
                )
                if str(row.get("is_nullable") or "").upper() == "NO":
                    item["table_schema"]["required"].append(column_name)
            grouped[(schema, table, object_type)] = item

        items = [grouped[key] for key in sorted(grouped.keys())]
        return CollectionDiscoveryResult(kind="sql_tables", items=items)


class ApiCollectionTypeProfile(BaseCollectionTypeProfile):
    collection_type = CollectionType.API.value

    def ensure_specific_fields(self, contract, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(fields)

    def expected_data_connector_subtype(self) -> Optional[str]:
        return "api"

    def supports_discovery(self) -> bool:
        return True

    async def discover(
        self,
        *,
        collection: Collection,
        session: AsyncSession,
        admin_user: Any,
    ) -> CollectionDiscoveryResult:
        if not collection.data_instance_id:
            raise InvalidSchemaError("API collection is not bound to data instance")

        result = await session.execute(
            select(ToolInstance).where(ToolInstance.id == collection.data_instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise InvalidSchemaError("Data instance not found")
        if str(instance.connector_subtype or "").strip().lower() != "api":
            raise InvalidSchemaError(
                "Collection is bound to non-API instance. "
                "Bind collection to a data connector with connector_subtype=api."
            )

        discovered: dict[str, dict[str, Any]] = {}

        version_entity_types = (
            (collection.current_version.semantic_profile or {}).get("entity_types", [])
            if collection.current_version is not None
            else []
        )
        for raw in version_entity_types:
            entity_type = str(raw or "").strip()
            if entity_type:
                discovered[entity_type] = {"entity_type": entity_type, "aliases": [], "examples": []}

        source_entities = ((collection.source_contract or {}).get("entities") or [])
        if isinstance(source_entities, list):
            for raw in source_entities:
                if not isinstance(raw, dict):
                    continue
                entity_type = str(raw.get("entity_type") or raw.get("name") or "").strip()
                if not entity_type:
                    continue
                aliases = [str(item).strip() for item in (raw.get("aliases") or []) if str(item).strip()]
                examples = [str(item).strip() for item in (raw.get("examples") or []) if str(item).strip()]
                discovered[entity_type] = {
                    "entity_type": entity_type,
                    "aliases": aliases,
                    "examples": examples,
                }

        object_types = ((instance.config or {}).get("object_types") or [])
        if isinstance(object_types, list):
            for raw in object_types:
                if isinstance(raw, str):
                    entity_type = raw.strip()
                    if entity_type and entity_type not in discovered:
                        discovered[entity_type] = {"entity_type": entity_type, "aliases": [], "examples": []}
                    continue
                if isinstance(raw, dict):
                    entity_type = str(raw.get("entity_type") or raw.get("name") or "").strip()
                    if not entity_type:
                        continue
                    aliases = [str(item).strip() for item in (raw.get("aliases") or []) if str(item).strip()]
                    examples = [str(item).strip() for item in (raw.get("examples") or []) if str(item).strip()]
                    discovered[entity_type] = {
                        "entity_type": entity_type,
                        "aliases": aliases,
                        "examples": examples,
                    }

        items = [discovered[key] for key in sorted(discovered.keys())]
        return CollectionDiscoveryResult(kind="api_entities", items=items)


_PROFILES: dict[str, BaseCollectionTypeProfile] = {
    CollectionType.TABLE.value: TableCollectionTypeProfile(),
    CollectionType.DOCUMENT.value: DocumentCollectionTypeProfile(),
    CollectionType.SQL.value: SqlCollectionTypeProfile(),
    CollectionType.API.value: ApiCollectionTypeProfile(),
}


def get_collection_type_profile(collection_type: str) -> BaseCollectionTypeProfile:
    normalized = str(collection_type or "").strip().lower()
    profile = _PROFILES.get(normalized)
    if profile is None:
        raise InvalidSchemaError(f"Unsupported collection type '{collection_type}'")
    return profile


def _coerce_user_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _json_type_for_pg(data_type: str, udt_name: str | None) -> dict[str, Any]:
    normalized = str(data_type or "").strip().lower()
    udt = str(udt_name or "").strip().lower()
    if normalized in {"integer", "smallint", "bigint"}:
        return {"type": "integer"}
    if normalized in {"numeric", "decimal", "real", "double precision"}:
        return {"type": "number"}
    if normalized in {"boolean"}:
        return {"type": "boolean"}
    if normalized in {"json", "jsonb"}:
        return {"type": "object"}
    if normalized in {"date"}:
        return {"type": "string", "format": "date"}
    if normalized in {"timestamp without time zone", "timestamp with time zone"}:
        return {"type": "string", "format": "date-time"}
    if normalized == "array" or udt.startswith("_"):
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "string"}


def _build_postgres_dsn(
    *,
    instance_url: str,
    database_name: str | None,
    username: str | None,
    password: str | None,
) -> str:
    raw_url = str(instance_url or "").strip()
    parsed = urlparse(raw_url)
    if not parsed.hostname:
        parsed = urlparse(f"//{raw_url}")
    if not parsed.hostname:
        raise ValueError("SQL connector url must contain host")

    db_name = (database_name or "").strip() or (parsed.path or "").strip("/ ")
    if not db_name:
        raise ValueError("database_name is required for SQL discovery")

    db_user = (username or "").strip() or (parsed.username or "").strip()
    db_password = (password or "").strip() or (parsed.password or "").strip()
    if not db_user or not db_password:
        raise ValueError("SQL discovery requires basic credentials with username/password")

    host = parsed.hostname
    port = parsed.port or 5432
    netloc = f"{quote(db_user)}:{quote(db_password)}@{host}:{port}"
    return f"postgresql://{netloc}/{db_name}"


def _sql_literal(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"
