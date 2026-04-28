from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.collection_readiness import CollectionReadinessBuilder
from app.agents.contracts import CollectionRuntimeStatus, ProviderExecutionTarget, ResolvedOperation
from app.agents.data_instance_resolver import AllowedDataInstance
from app.agents.operation_router import OperationRouter


def _operation(*, instance_slug: str, source: str = "local", has_credentials: bool = True) -> ResolvedOperation:
    operation_slug = f"instance.{instance_slug}.search"
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="mcp" if source == "mcp" else "local",
        data_instance_id=f"inst-{instance_slug}",
        data_instance_slug=instance_slug,
        has_credentials=has_credentials,
    )
    return ResolvedOperation(
        operation_slug=operation_slug,
        operation="search",
        name=operation_slug,
        data_instance_id=f"inst-{instance_slug}",
        data_instance_slug=instance_slug,
        source=source,  # type: ignore[arg-type]
        target=target,
    )


def test_collection_runtime_readiness_table_ready():
    builder = CollectionReadinessBuilder(schema_stale_after_hours=24)
    collection = SimpleNamespace(
        id=uuid4(),
        slug="tickets",
        collection_type="table",
        current_version_id=uuid4(),
        current_version=SimpleNamespace(version=3, status="published"),
        schema_status="ready",
        last_sync_at=None,
    )
    instance = SimpleNamespace(id=uuid4(), slug="tickets_data", is_remote=False)

    readiness = builder.build(
        collection=collection,
        data_instance=instance,
        provider_instance=instance,
        operations=[_operation(instance_slug="tickets_data")],
        collection_snapshot={"status": "ready"},
    )

    assert readiness.status == CollectionRuntimeStatus.READY
    assert readiness.schema_freshness == "fresh"
    assert readiness.available_operations == ["instance.tickets_data.search"]


def test_collection_runtime_readiness_document_requires_ready_pipeline():
    builder = CollectionReadinessBuilder(schema_stale_after_hours=24)
    collection = SimpleNamespace(
        id=uuid4(),
        slug="docs",
        collection_type="document",
        current_version_id=None,
        current_version=None,
        schema_status="ingesting",
        last_sync_at=None,
    )
    instance = SimpleNamespace(id=uuid4(), slug="docs_data", is_remote=False)

    readiness = builder.build(
        collection=collection,
        data_instance=instance,
        provider_instance=instance,
        operations=[_operation(instance_slug="docs_data")],
        collection_snapshot={"status": "ingesting"},
    )

    assert readiness.status == CollectionRuntimeStatus.SCHEMA_STALE
    assert readiness.schema_freshness == "stale"
    assert "schema_stale" in readiness.missing_requirements


def test_collection_runtime_readiness_sql_stale_when_last_sync_outdated():
    builder = CollectionReadinessBuilder(schema_stale_after_hours=24)
    collection = SimpleNamespace(
        id=uuid4(),
        slug="warehouse_sql",
        collection_type="sql",
        current_version_id=None,
        current_version=None,
        schema_status="ready",
        last_sync_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    instance = SimpleNamespace(id=uuid4(), slug="warehouse_sql_data", is_remote=True)

    readiness = builder.build(
        collection=collection,
        data_instance=instance,
        provider_instance=instance,
        operations=[_operation(instance_slug="warehouse_sql_data", source="mcp", has_credentials=True)],
        collection_snapshot={"status": "ready"},
    )

    assert readiness.status == CollectionRuntimeStatus.SCHEMA_STALE
    assert readiness.schema_freshness == "stale"


@pytest.mark.asyncio
async def test_operation_router_marks_missing_credentials_in_readiness_and_missing_requirements():
    router = OperationRouter(session=SimpleNamespace())

    data_instance = SimpleNamespace(
        id=uuid4(),
        slug="sql_data",
        name="SQL data",
        placement="remote",
        description="",
        config={},
        url="http://provider",
        health_status="healthy",
    )
    provider = SimpleNamespace(
        id=uuid4(),
        slug="sql_provider",
        config={},
        url="http://provider",
        health_status="healthy",
        is_remote=True,
    )
    collection = SimpleNamespace(
        id=uuid4(),
        slug="warehouse_sql",
        description="",
        entity_type="ticket",
        collection_type="sql",
        table_schema={"tables": [{"name": "tickets"}]},
        source_contract={},
        current_version=None,
        current_version_id=None,
        schema_status="ready",
        last_sync_at=datetime.now(timezone.utc),
    )
    operation = _operation(instance_slug="sql_data", source="mcp", has_credentials=False)
    allowed_instance = AllowedDataInstance(
        instance=data_instance,
        provider=provider,
        collection=collection,
        readiness_reason="ready",
        runtime_domain="collection.sql",
    )

    router.data_instance_resolver = SimpleNamespace(resolve=AsyncMock(return_value=[allowed_instance]))
    router.collection_status_snapshot = SimpleNamespace(
        get_status_snapshot=AsyncMock(return_value={"status": "ready"})
    )
    router.operation_resolver = SimpleNamespace(
        resolve_for_instance=AsyncMock(return_value=[(operation, None)])
    )
    router.runtime_rbac_resolver = SimpleNamespace(
        is_collection_allowed=lambda **_kwargs: True,
    )
    effective_permissions = SimpleNamespace()

    result = await router.resolve(
        user_id=uuid4(),
        tenant_id=uuid4(),
        effective_permissions=effective_permissions,
    )

    assert result.missing.credentials == ["sql_data"]
    assert result.resolved_data_instances[0].readiness is not None
    assert (
        result.resolved_data_instances[0].readiness.status
        == CollectionRuntimeStatus.DEGRADED_MISSING_CREDENTIALS
    )
