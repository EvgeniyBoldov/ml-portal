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
        publication=None,
        operation_name="file.read",
        title="Read file",
        description="Read a file from the runtime workspace",
        input_schema={},
        output_schema={},
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
