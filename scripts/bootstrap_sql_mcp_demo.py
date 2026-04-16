from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import _db_url
from app.models.discovered_tool import DiscoveredTool
from app.models.tool_release import ToolBackendRelease
from app.schemas.tool_releases import ToolReleaseCreate
from app.schemas.tools import ToolCreate
from app.services.tool_discovery_service import ToolDiscoveryService
from app.services.tool_instance_service import ToolInstanceService
from app.services.tool_release_service import ToolReleaseService
from app.services.tool_service import ToolService


PROVIDER_SLUG = "mcp-sql-dbhub"
DATA_SLUG = "external-it-tickets-db"
PROVIDER_URL = "http://dbhub-mcp:8080/"
REMOTE_DSN = "postgresql://external_user:external_password@postgres-remote:5432/external_analytics"

TOOL_OVERRIDES = {
    "execute_sql": {
        "title": "SQL Execute",
        "description": (
            "Run read-only SQL against the external IT tickets PostgreSQL database. "
            "Use for targeted tabular analysis when table and field names are already known."
        ),
        "side_effects": "none",
        "risk_level": "medium",
        "idempotent": True,
        "requires_confirmation": False,
        "examples": [
            {
                "title": "Open incidents by keyword",
                "arguments": {
                    "sql": "SELECT number, title FROM it_tickets WHERE body ILIKE '%switch%' ORDER BY number LIMIT 5",
                },
            }
        ],
    },
    "search_objects": {
        "title": "SQL Schema Search",
        "description": "Search tables and columns in the external PostgreSQL catalog before composing SQL queries.",
        "side_effects": "none",
        "risk_level": "low",
        "idempotent": True,
        "requires_confirmation": False,
        "examples": [
            {
                "title": "Find ticket-related objects",
                "arguments": {
                    "query": "ticket",
                    "object_types": ["table", "column"],
                    "limit": 20,
                },
            }
        ],
    },
}

RELEASE_CREATE = {
    "execute_sql": ToolReleaseCreate(
        backend_release_id=None,
        routing_resource="sql",
        routing_ops=["read", "query"],
        routing_systems=["postgres"],
        routing_risk_level="medium",
        routing_requires_confirmation=False,
        routing_idempotent=True,
        routing_side_effects="none",
        routing_input_hints=["Pass a read-only SQL query", "Prefer explicit column lists and LIMIT"],
        routing_output_hints=["Returns rows, columns, row_count, truncated flag"],
        routing_keywords=["sql", "query", "select", "postgres", "tickets"],
        routing_negative_keywords=["delete", "update", "insert", "drop"],
        exec_timeout_s=20,
        exec_max_retries=0,
        exec_max_concurrency=1,
        exec_priority="normal",
        description_for_llm="Executes a read-only SQL query against the external IT tickets PostgreSQL database.",
        field_hints={
            "sql": "Read-only SQL only. Prefer SELECT with explicit columns and LIMIT.",
            "limit": "Optional hard limit appended when SQL has no LIMIT clause.",
        },
        examples=TOOL_OVERRIDES["execute_sql"]["examples"],
        return_summary="Returns tabular rows from the remote PostgreSQL database.",
        common_errors=["Only read-only SELECT/WITH/EXPLAIN statements are allowed"],
        notes="Created from SQL MCP discovery bootstrap.",
    ),
    "search_objects": ToolReleaseCreate(
        backend_release_id=None,
        routing_resource="sql",
        routing_ops=["discover", "schema"],
        routing_systems=["postgres"],
        routing_risk_level="low",
        routing_requires_confirmation=False,
        routing_idempotent=True,
        routing_side_effects="none",
        routing_input_hints=["Use before execute_sql when schema is unknown"],
        routing_output_hints=["Returns matching tables/views/columns from information_schema"],
        routing_keywords=["schema", "columns", "tables", "postgres", "catalog"],
        routing_negative_keywords=["write", "mutate"],
        exec_timeout_s=10,
        exec_max_retries=0,
        exec_max_concurrency=1,
        exec_priority="normal",
        description_for_llm="Searches the external PostgreSQL catalog for tables, views, and columns.",
        field_hints={
            "query": "Free-text search across table names, schema names, and column names.",
            "schema": "Optional schema filter.",
            "object_types": "Restrict search to table, view, or column.",
            "limit": "Maximum number of catalog items to return.",
        },
        examples=TOOL_OVERRIDES["search_objects"]["examples"],
        return_summary="Returns matching schema objects from the remote PostgreSQL catalog.",
        common_errors=["Session not initialized"],
        notes="Created from SQL MCP discovery bootstrap.",
    ),
}


async def ensure_instance(
    service: ToolInstanceService,
    *,
    slug: str,
    name: str,
    instance_kind: str,
    placement: str,
    domain: str,
    url: str,
    description: str,
    config: dict,
    access_via_instance_id=None,
):
    existing = await service.repo.get_by_slug(slug)
    if existing:
        return await service.update_instance(
            existing.id,
            name=name,
            description=description,
            instance_kind=instance_kind,
            placement=placement,
            domain=domain,
            url=url,
            config=config,
            access_via_instance_id=access_via_instance_id,
            is_active=True,
        )
    return await service.create_instance(
        slug=slug,
        name=name,
        instance_kind=instance_kind,
        placement=placement,
        domain=domain,
        url=url,
        description=description,
        config=config,
        access_via_instance_id=access_via_instance_id,
    )


async def main() -> None:
    engine = create_async_engine(_db_url(), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        instance_service = ToolInstanceService(session)
        provider = await ensure_instance(
            instance_service,
            slug=PROVIDER_SLUG,
            name="DBHub SQL MCP",
            instance_kind="service",
            placement="remote",
            domain="mcp",
            url=PROVIDER_URL,
            description="Read-only SQL MCP provider for remote PostgreSQL exploration.",
            config={
                "provider_kind": "sql-mcp",
                "transport": "http",
                "upstream": "dbhub-shim",
                "readonly": True,
            },
        )
        data_instance = await ensure_instance(
            instance_service,
            slug=DATA_SLUG,
            name="External IT Tickets DB",
            instance_kind="data",
            placement="remote",
            domain="sql",
            url=REMOTE_DSN,
            description="Remote PostgreSQL database with IT tickets for SQL/MCP discovery and analysis tests.",
            config={
                "db_type": "postgresql",
                "database": "external_analytics",
                "host": "postgres-remote",
                "port": 5432,
                "schema": "public",
                "catalog_mode": "remote_sql",
                "capabilities": ["schema_discovery", "read_only_sql"],
            },
            access_via_instance_id=provider.id,
        )

        profiles = await instance_service.list_semantic_versions(data_instance.id)
        active_profile = next((p for p in profiles if p.status == "active"), None)
        if active_profile is None:
            profile = await instance_service.create_semantic_version(
                data_instance.id,
                summary="Remote PostgreSQL database with IT support tickets.",
                entity_types=["ticket", "incident", "task"],
                use_cases=(
                    "Use to inspect ticket history, search incidents by infrastructure clues, "
                    "aggregate issues by keyword or symptom, and test remote SQL analysis flows."
                ),
                limitations=(
                    "Read-only access only. Current semantic profile covers the public.it_tickets "
                    "table discovered for sandbox experiments."
                ),
                freshness_notes="Seeded from it_tickets_template.csv during local environment bootstrap.",
                examples={
                    "queries": [
                        "Find tickets mentioning sw2-core-DC",
                        "Count incidents mentioning PostgreSQL latency",
                    ]
                },
                schema_hints={
                    "tables": {
                        "public.it_tickets": {
                            "description": "Normalized ITSM-style tickets loaded from template CSV.",
                            "columns": {
                                "number": "Ticket identifier",
                                "title": "Short summary",
                                "body": "Detailed problem description",
                            },
                            "primary_key": ["number"],
                        }
                    }
                },
                notes="Bootstrap semantic layer for remote SQL instance.",
            )
            await instance_service.activate_semantic_version(data_instance.id, profile.version)

        discovery = ToolDiscoveryService(session)
        stats = await discovery.rescan(include_local=False, provider_instance_id=provider.id)
        print("rescan_stats", stats)

        discovered = list(
            (
                await session.execute(
                    select(DiscoveredTool)
                    .where(DiscoveredTool.provider_instance_id == provider.id)
                    .order_by(DiscoveredTool.slug)
                )
            )
            .scalars()
            .all()
        )
        print("discovered", [tool.slug for tool in discovered])

        tool_service = ToolService(session)
        release_service = ToolReleaseService(session)

        for discovered_tool in discovered:
            discovered_tool.use_in_runtime = True
            discovered_tool.is_active = True
            discovered_tool.profile_override = TOOL_OVERRIDES.get(discovered_tool.slug, {})
            discovered_tool.updated_at = datetime.now(timezone.utc)

            tool = await tool_service.repo.get_by_slug(discovered_tool.slug)
            if tool is None:
                tool = await tool_service.create_tool(
                    ToolCreate(
                        slug=discovered_tool.slug,
                        name=discovered_tool.name,
                        domains=["sql"],
                        short_info=discovered_tool.description,
                        tags=["sql", "mcp", "remote-db"],
                        is_routable=True,
                        routing_keywords=["sql", "postgres", "database", "tickets"],
                        routing_negative_keywords=["write", "delete"],
                    )
                )

            backend_release = await release_service.backend_repo.get_by_tool_and_version(tool.id, "mcp-v1")
            if backend_release is None:
                backend_release = ToolBackendRelease(
                    tool_id=tool.id,
                    version="mcp-v1",
                    input_schema=discovered_tool.input_schema or {},
                    output_schema=discovered_tool.output_schema,
                    description=discovered_tool.description,
                    method_name=discovered_tool.slug,
                    deprecated=False,
                    schema_hash=None,
                    worker_build_id="dbhub-mcp-shim",
                    last_seen_at=datetime.now(timezone.utc),
                    synced_at=datetime.now(timezone.utc),
                )
                session.add(backend_release)
                await session.flush()
            else:
                backend_release.input_schema = discovered_tool.input_schema or {}
                backend_release.output_schema = discovered_tool.output_schema
                backend_release.description = discovered_tool.description
                backend_release.method_name = discovered_tool.slug
                backend_release.worker_build_id = "dbhub-mcp-shim"
                backend_release.last_seen_at = datetime.now(timezone.utc)
                backend_release.synced_at = datetime.now(timezone.utc)
                await session.flush()

            active_release = await release_service.release_repo.get_active(tool.id)
            if active_release is None:
                payload = RELEASE_CREATE[discovered_tool.slug].model_copy(
                    update={"backend_release_id": backend_release.id}
                )
                created = await release_service.create_release_by_tool_id(tool.id, payload)
                await release_service.activate_release_by_tool_id(tool.id, created.version)

        await session.commit()
        print("provider_id", provider.id)
        print("data_instance_id", data_instance.id)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
