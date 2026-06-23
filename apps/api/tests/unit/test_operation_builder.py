from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.operation_builder import OperationBuilder


@pytest.mark.asyncio
async def test_system_tool_uses_stable_data_instance_sentinel() -> None:
    tool_resolver = AsyncMock()
    tool_resolver.resolve.return_value = SimpleNamespace(
        publication=SimpleNamespace(canonical_op_slug="file.read", scope_kind="system"),
        operation_name="file.read",
        title="Read file",
        description="Read a file from the runtime workspace",
        input_schema={},
        output_schema={},
        domain="system",
        result_kind="file",
        scope_kind="system",
        credential_scope="auto",
        risk_level="safe",
        side_effects=False,
        idempotent=True,
        requires_confirmation=False,
        risk_flags=[],
    )

    builder = OperationBuilder(
        tool_resolver=tool_resolver,
        runtime_rbac_resolver=SimpleNamespace(),
    )

    instance = SimpleNamespace(id=uuid4(), slug="system", url=None, is_local=True, health_status="healthy")
    discovered_tool = SimpleNamespace(slug="file.read", source="local", domains=["system"])

    built = await builder._build_single_operation(
        discovered_tool=discovered_tool,
        instance=instance,
        provider=instance,
        has_credentials=True,
        runtime_domain="system",
        context_domains=["system"],
        effective_permissions=None,
        user_id=uuid4(),
        tenant_id=uuid4(),
        seen_operation_slugs=set(),
        resolve_execution_credentials=AsyncMock(return_value=None),
    )

    assert built is not None
    operation, target_credentials = built
    assert target_credentials is None
    assert operation.scope == "system"
    assert operation.data_instance_id == "system"
    assert operation.data_instance_slug == "system"
    assert operation.target.data_instance_id == "system"
    assert operation.target.data_instance_slug == "system"


@pytest.mark.asyncio
async def test_template_builtin_is_published_as_collection_operation() -> None:
    tool_resolver = AsyncMock()
    tool_resolver.resolve.return_value = SimpleNamespace(
        publication=SimpleNamespace(canonical_op_slug="collection.template.fill", scope_kind="collection"),
        operation_name="collection.template.fill",
        title="Fill Template",
        description="Fill a template with values and return a generated file",
        input_schema={"properties": {"template_id": {"type": "string"}}, "required": ["template_id"]},
        output_schema={},
        domain="collection.template",
        result_kind="file",
        scope_kind="collection",
        credential_scope="auto",
        risk_level="safe",
        side_effects=False,
        idempotent=True,
        requires_confirmation=False,
        risk_flags=[],
    )

    builder = OperationBuilder(
        tool_resolver=tool_resolver,
        runtime_rbac_resolver=SimpleNamespace(),
    )

    instance = SimpleNamespace(id=uuid4(), slug="template-data", url=None, is_local=True, health_status="healthy")
    discovered_tool = SimpleNamespace(slug="template.fill", source="local", domains=["system"])

    built = await builder._build_single_operation(
        discovered_tool=discovered_tool,
        instance=instance,
        provider=instance,
        has_credentials=True,
        runtime_domain="collection.template",
        context_domains=["collection.template"],
        effective_permissions=None,
        user_id=uuid4(),
        tenant_id=uuid4(),
        seen_operation_slugs=set(),
        resolve_execution_credentials=AsyncMock(return_value=None),
    )

    assert built is not None
    operation, _ = built
    assert operation.scope == "collection"
    assert operation.operation == "collection.template.fill"
    assert operation.operation_slug == "instance.template-data.collection.template.fill"
    assert operation.raw_tool_slug == "template.fill"
    assert operation.result_kind == "file"
    assert operation.data_instance_slug == "template-data"
