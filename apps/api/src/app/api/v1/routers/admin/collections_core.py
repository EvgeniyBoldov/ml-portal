"""
Admin collection core CRUD endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.collection_readiness import CollectionReadinessBuilder
from app.agents.contracts import CollectionRuntimeReadiness, CollectionRuntimeStatus
from app.agents.credential_resolver import CredentialsUnavailableError
from app.agents.operation_router import OperationRouter
from app.api.deps import db_uow, require_admin
from app.core.config import get_settings
from app.core.exceptions import InvalidSchemaError
from app.models.collection import Collection, CollectionType
from app.models.tool_instance import ToolInstance
from app.schemas.collections import (
    DiscoverApiEntitiesResponse,
    CollectionListResponse,
    CollectionResponse,
    CreateCollectionRequest,
    DiscoveredApiEntity,
    DiscoverSqlTablesResponse,
    DiscoveredSqlTable,
    UpdateCollectionRequest,
)
from app.services.credential_service import CredentialService
from app.services.mcp_jsonrpc_client import (
    mcp_call_tool,
    mcp_initialize,
    mcp_result_error_message,
)
from app.services.collection_service import CollectionService, _UNSET

from .collections_shared import build_collection_response

router = APIRouter()


def _json_schema_type_from_sql_type(sql_type: str | None) -> tuple[str, str | None]:
    normalized = str(sql_type or "").strip().lower()
    if normalized in {"smallint", "integer", "bigint"}:
        return "integer", None
    if normalized in {"numeric", "decimal", "real", "double precision", "float", "money"}:
        return "number", None
    if normalized in {"boolean"}:
        return "boolean", None
    if normalized in {"json", "jsonb"}:
        return "object", None
    if normalized in {"date"}:
        return "string", "date"
    if normalized.startswith("timestamp"):
        return "string", "date-time"
    if normalized.startswith("time"):
        return "string", "time"
    return "string", None


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
        raise ValueError("SQL connector URL must include hostname")

    db_name = (database_name or "").strip() or (parsed.path or "").strip("/ ")
    if not db_name:
        raise ValueError("database_name is required")

    user = (username or "").strip() or (parsed.username or "").strip()
    pwd = (password or "").strip() or (parsed.password or "").strip()
    if not user or not pwd:
        raise ValueError("username/password are required")

    port = parsed.port or 5432
    credentials = f"{quote(user)}:{quote(pwd)}"
    return f"postgresql://{credentials}@{parsed.hostname}:{port}/{db_name}"


async def _discover_sql_tables_via_connector(
    session: AsyncSession,
    collection: Collection,
) -> list[dict]:
    if not collection.data_instance_id:
        return []

    data_result = await session.execute(
        select(ToolInstance).where(ToolInstance.id == collection.data_instance_id)
    )
    data_instance = data_result.scalar_one_or_none()
    if not data_instance:
        return []

    provider = None
    if data_instance.access_via_instance_id:
        provider_result = await session.execute(
            select(ToolInstance).where(ToolInstance.id == data_instance.access_via_instance_id)
        )
        provider = provider_result.scalar_one_or_none()
    if not provider:
        return []
    if str(getattr(provider, "connector_type", "") or "").strip().lower() != "mcp":
        return []
    provider_url = str(getattr(provider, "url", "") or "").strip()
    if not provider_url:
        return []

    session_id = await mcp_initialize(provider_url=provider_url, timeout_s=10)
    creds = await CredentialService(session).resolve_credentials(
        instance_id=data_instance.id,
        strategy="PLATFORM_FIRST",
    )
    payload = (creds.payload or {}) if creds else {}
    arguments = {
        "sql": (
            "SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name, ordinal_position"
        )
    }
    try:
        arguments["db_dsn"] = _build_postgres_dsn(
            instance_url=data_instance.url,
            database_name=(data_instance.config or {}).get("database_name"),
            username=payload.get("username"),
            password=payload.get("password"),
        )
    except ValueError:
        pass

    result = await mcp_call_tool(
        provider_url=provider_url,
        session_id=session_id,
        tool_name="execute_sql",
        arguments=arguments,
        timeout_s=30,
    )
    tool_error = mcp_result_error_message(result)
    if tool_error:
        raise InvalidSchemaError(f"SQL discovery failed: {tool_error}")

    rows = (result.get("structuredContent") or {}).get("rows") or []
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        schema_name = str(row.get("table_schema") or "public").strip() or "public"
        table_name = str(row.get("table_name") or "").strip()
        column_name = str(row.get("column_name") or "").strip()
        if not table_name or not column_name:
            continue
        key = (schema_name, table_name)
        grouped.setdefault(key, []).append(
            {
                "name": column_name,
                "type": str(row.get("data_type") or "").strip(),
                "nullable": str(row.get("is_nullable") or "").strip().upper() == "YES",
            }
        )

    discovered: list[dict] = []
    for (schema_name, table_name), columns in sorted(grouped.items()):
        properties: dict[str, dict] = {}
        for col in columns:
            json_type, json_format = _json_schema_type_from_sql_type(col.get("type"))
            spec: dict[str, str] = {"type": json_type}
            if json_format:
                spec["format"] = json_format
            properties[str(col["name"])] = spec
        discovered.append(
            {
                "schema_name": schema_name,
                "table_name": table_name,
                "object_type": "BASE TABLE",
                "table_schema": {"type": "object", "properties": properties},
            }
        )
    return discovered


def _extract_remote_sql_tables(table_schema: dict | None, source_contract: dict | None) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _push(schema_name: str | None, table_name: str | None, columns=None) -> None:
        table = str(table_name or "").strip()
        if not table:
            return
        schema = str(schema_name or "").strip() or "public"
        key = (schema, table)
        if key in seen:
            return
        seen.add(key)
        result.append(
            {
                "schema_name": schema,
                "table_name": table,
                "object_type": "BASE TABLE",
                "table_schema": {"columns": columns} if isinstance(columns, list) else {},
            }
        )

    for source in (table_schema, source_contract):
        if not isinstance(source, dict):
            continue

        tables = source.get("tables")
        if isinstance(tables, list):
            for item in tables:
                if isinstance(item, str):
                    _push(None, item)
                elif isinstance(item, dict):
                    _push(item.get("schema"), item.get("name") or item.get("table"), item.get("columns"))

        schemas = source.get("schemas")
        if isinstance(schemas, list):
            for schema_obj in schemas:
                if not isinstance(schema_obj, dict):
                    continue
                schema_name = schema_obj.get("schema") or schema_obj.get("name")
                schema_tables = schema_obj.get("tables")
                if isinstance(schema_tables, list):
                    for item in schema_tables:
                        if isinstance(item, str):
                            _push(schema_name, item)
                        elif isinstance(item, dict):
                            _push(schema_name, item.get("name") or item.get("table"), item.get("columns"))
        elif isinstance(schemas, dict):
            for schema_name, schema_tables in schemas.items():
                if isinstance(schema_tables, list):
                    for item in schema_tables:
                        if isinstance(item, str):
                            _push(schema_name, item)
                        elif isinstance(item, dict):
                            _push(schema_name, item.get("name") or item.get("table"), item.get("columns"))

    result.sort(key=lambda item: (item["schema_name"], item["table_name"]))
    return result


def _normalize_sql_discovery_schema(discovered: list[dict]) -> dict:
    schemas: dict[str, list[dict]] = {}
    for item in discovered:
        if not isinstance(item, dict):
            continue
        schema_name = str(item.get("schema_name") or "public").strip() or "public"
        table_name = str(item.get("table_name") or "").strip()
        if not table_name:
            continue
        table_schema = item.get("table_schema") if isinstance(item.get("table_schema"), dict) else {}
        properties = table_schema.get("properties") if isinstance(table_schema, dict) else {}
        columns: list[dict] = []
        if isinstance(properties, dict):
            for column_name, spec in properties.items():
                data_type = ""
                if isinstance(spec, dict):
                    data_type = str(spec.get("type") or spec.get("format") or "").strip()
                columns.append(
                    {
                        "name": str(column_name),
                        "data_type": data_type,
                    }
                )
        schemas.setdefault(schema_name, []).append(
            {
                "name": table_name,
                "table": table_name,
                "columns": columns,
            }
        )

    schema_list: list[dict] = []
    for schema_name in sorted(schemas.keys()):
        tables = sorted(
            schemas[schema_name],
            key=lambda value: str(value.get("name") or value.get("table") or "").lower(),
        )
        schema_list.append({"schema": schema_name, "tables": tables})
    return {"schemas": schema_list}


def _extract_api_entities(table_schema: dict | None, source_contract: dict | None) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()

    def _norm_list(value) -> list[str]:
        if isinstance(value, list):
            values = value
        elif isinstance(value, str):
            values = [value]
        else:
            values = []
        normalized: list[str] = []
        for item in values:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    def _push(entity_type: str | None, aliases=None, examples=None) -> None:
        entity = str(entity_type or "").strip()
        if not entity:
            return
        key = entity.lower()
        if key in seen:
            return
        seen.add(key)
        result.append(
            {
                "entity_type": entity,
                "aliases": _norm_list(aliases),
                "examples": _norm_list(examples),
            }
        )

    for source in (table_schema, source_contract):
        if not isinstance(source, dict):
            continue

        entities = source.get("entities")
        if isinstance(entities, list):
            for item in entities:
                if isinstance(item, str):
                    _push(item)
                elif isinstance(item, dict):
                    _push(
                        item.get("entity_type") or item.get("name") or item.get("resource"),
                        item.get("aliases"),
                        item.get("examples"),
                    )

        entity_types = source.get("entity_types")
        if isinstance(entity_types, list):
            for item in entity_types:
                if isinstance(item, str):
                    _push(item)

        resources = source.get("resources")
        if isinstance(resources, list):
            for item in resources:
                if isinstance(item, dict):
                    _push(
                        item.get("entity_type") or item.get("name") or item.get("resource"),
                        item.get("aliases"),
                        item.get("examples"),
                    )

    result.sort(key=lambda item: item["entity_type"].lower())
    return result


@router.get("/", response_model=CollectionListResponse)
async def list_all_collections(
    page: int = 1,
    size: int = 20,
    tenant_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    query = select(Collection).options(
        selectinload(Collection.schema),
        selectinload(Collection.current_version),
        selectinload(Collection.data_instance),
    )
    if tenant_id:
        query = query.where(Collection.tenant_id == tenant_id)
    if is_active is not None:
        query = query.where(Collection.is_active == is_active)
    query = query.order_by(Collection.created_at.desc())

    result = await session.execute(query)
    all_collections = list(result.scalars().all())

    total = len(all_collections)
    start_idx = (page - 1) * size
    end_idx = start_idx + size
    items = all_collections[start_idx:end_idx]

    response_items = []
    service = CollectionService(session)
    for c in items:
        response_items.append(await build_collection_response(service, c))

    return CollectionListResponse(
        items=response_items,
        total=total,
        page=page,
        size=size,
        has_more=end_idx < total,
    )


@router.post("/", response_model=CollectionResponse)
async def create_collection(
    body: CreateCollectionRequest,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    from sqlalchemy.future import select as sa_select

    resolved_tenant_id = body.tenant_id
    if resolved_tenant_id is None:
        for raw_tenant_id in (admin_user.tenant_ids or []):
            try:
                resolved_tenant_id = uuid.UUID(str(raw_tenant_id))
                break
            except (TypeError, ValueError):
                continue
    if resolved_tenant_id is None:
        raise HTTPException(status_code=400, detail="tenant_id is required when user has no tenant context")

    service = CollectionService(session)
    collection = await service.create_collection(
        tenant_id=resolved_tenant_id,
        slug=body.slug,
        name=body.name,
        description=body.description,
        fields=[f.model_dump() for f in body.fields],
        source_contract=body.source_contract,
        vector_config=body.vector_config.model_dump() if body.vector_config else None,
        collection_type=body.collection_type,
        data_instance_id=body.data_instance_id,
        table_schema=body.table_schema,
    )
    await session.commit()

    stmt = (
        sa_select(Collection)
        .options(
            selectinload(Collection.schema),
            selectinload(Collection.current_version),
            selectinload(Collection.data_instance),
        )
        .where(Collection.id == collection.id)
    )
    result = await session.execute(stmt)
    collection = result.scalar_one()
    return await build_collection_response(service, collection)


@router.post("/{collection_id}/discover-tables", response_model=DiscoverSqlTablesResponse)
async def discover_sql_tables(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if str(collection.collection_type or "").strip().lower() != CollectionType.SQL.value:
        raise HTTPException(status_code=400, detail="Table discovery is available only for sql collections")

    try:
        discovered = _extract_remote_sql_tables(
            collection.table_schema if isinstance(collection.table_schema, dict) else {},
            collection.source_contract if isinstance(collection.source_contract, dict) else {},
        )
        if not discovered:
            discovered = await _discover_sql_tables_via_connector(session, collection)
        if discovered:
            normalized_schema = _normalize_sql_discovery_schema(discovered)
            collection.table_schema = normalized_schema
            collection.last_sync_at = datetime.now(timezone.utc)
            await session.flush()
            await session.commit()
    except InvalidSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = [DiscoveredSqlTable(**item) for item in discovered]
    return DiscoverSqlTablesResponse(items=items, total=len(items))


@router.post("/{collection_id}/discover-entities", response_model=DiscoverApiEntitiesResponse)
async def discover_api_entities(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if str(collection.collection_type or "").strip().lower() != CollectionType.API.value:
        raise HTTPException(status_code=400, detail="Entity discovery is available only for api collections")

    try:
        discovered = _extract_api_entities(
            collection.table_schema if isinstance(collection.table_schema, dict) else {},
            collection.source_contract if isinstance(collection.source_contract, dict) else {},
        )
        if not discovered and collection.entity_type:
            discovered = [
                {
                    "entity_type": collection.entity_type,
                    "aliases": [],
                    "examples": [],
                }
            ]
    except InvalidSchemaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = [DiscoveredApiEntity(**item) for item in discovered]
    return DiscoverApiEntitiesResponse(items=items, total=len(items))


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return await build_collection_response(service, collection)


@router.get("/{collection_id}/runtime-readiness", response_model=CollectionRuntimeReadiness)
async def get_collection_runtime_readiness(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    user_id = uuid.UUID(str(admin_user.id))
    tenant_id = collection.tenant_id
    return await _build_collection_runtime_readiness(
        session=session,
        collection=collection,
        user_id=user_id,
        tenant_id=tenant_id,
    )


@router.put("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: uuid.UUID,
    body: UpdateCollectionRequest,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.update_collection(
        collection_id=collection_id,
        name=body.name if "name" in body.model_fields_set else _UNSET,
        description=body.description if "description" in body.model_fields_set else _UNSET,
        is_active=body.is_active if "is_active" in body.model_fields_set else _UNSET,
        table_name=body.table_name if "table_name" in body.model_fields_set else _UNSET,
        table_schema=body.table_schema if "table_schema" in body.model_fields_set else _UNSET,
        schema_ops=[op.model_dump() for op in body.schema_ops],
    )
    await session.commit()
    await session.refresh(collection)
    return await build_collection_response(service, collection)


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    drop_table: bool = True,
    session: AsyncSession = Depends(db_uow),
    admin_user=Depends(require_admin),
):
    service = CollectionService(session)
    collection = await service.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    deleted = await service.delete_collection(collection.tenant_id, collection.slug, drop_table=drop_table)
    if not deleted:
        raise HTTPException(status_code=404, detail="Collection not found")

    await session.commit()
    return {"status": "deleted", "id": str(collection_id), "table_dropped": drop_table}
async def _build_collection_runtime_readiness(
    *,
    session: AsyncSession,
    collection: Collection,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> CollectionRuntimeReadiness:
    settings = get_settings()
    operation_router = OperationRouter(session)
    readiness_builder = CollectionReadinessBuilder(
        schema_stale_after_hours=getattr(settings, "COLLECTION_SCHEMA_STALE_HOURS", 24)
    )
    snapshot = await operation_router.collection_status_snapshot.get_status_snapshot(collection)
    data_instance = collection.data_instance
    if data_instance is None:
        return readiness_builder.build(
            collection=collection,
            data_instance=SimpleNamespace(
                id=None,
                slug=f"missing-data-instance-{collection.slug}",
                is_remote=True,
            ),
            provider_instance=None,
            operations=[],
            collection_snapshot=snapshot,
        )

    provider = data_instance
    if data_instance.access_via_instance_id:
        loaded = await operation_router.data_instance_resolver._load_provider_instance(data_instance)  # noqa: SLF001
        if loaded is not None:
            provider = loaded

    effective_permissions = await operation_router.runtime_rbac_resolver.resolve_effective_permissions(
        user_id=user_id,
        tenant_id=tenant_id,
        default_collection_allow=True,
    )
    operations = []
    try:
        operations = await operation_router.operation_resolver.resolve_for_instance(
            instance=data_instance,
            provider=provider,
            runtime_domain=operation_router.data_instance_resolver._resolve_runtime_domain(  # noqa: SLF001
                collection,
                data_instance,
            ),
            effective_permissions=effective_permissions,
            user_id=user_id,
            tenant_id=tenant_id,
            sandbox_overrides=None,
        )
    except CredentialsUnavailableError:
        operations = []

    readiness = readiness_builder.build(
        collection=collection,
        data_instance=data_instance,
        provider_instance=provider,
        operations=[item[0] for item in operations],
        collection_snapshot=snapshot,
    )
    if not operations and data_instance.is_remote and provider.is_remote:
        if "missing_credentials" not in readiness.missing_requirements:
            readiness.missing_requirements.append("missing_credentials")
        readiness.credential_status = "missing"
        readiness.status = CollectionRuntimeStatus.DEGRADED_MISSING_CREDENTIALS
    return readiness
