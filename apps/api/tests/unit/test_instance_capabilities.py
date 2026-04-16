from __future__ import annotations

from uuid import uuid4

from app.models.tool_instance import ToolInstance
from app.services.instance_capabilities import is_mcp_service_instance


def _instance(*, instance_kind: str, domain: str, config: dict | None = None) -> ToolInstance:
    return ToolInstance(
        id=uuid4(),
        slug=f"inst-{uuid4().hex[:8]}",
        name="Instance",
        description=None,
        instance_kind=instance_kind,
        placement="remote",
        domain=domain,
        url="https://example.org",
        config=config or {},
        is_active=True,
    )


def test_is_mcp_service_instance_prefers_provider_kind_flag():
    instance = _instance(
        instance_kind="service",
        domain="jira",
        config={"provider_kind": "mcp"},
    )

    assert is_mcp_service_instance(instance) is True


def test_is_mcp_service_instance_requires_explicit_provider_kind():
    instance = _instance(
        instance_kind="service",
        domain="mcp",
        config={},
    )

    assert is_mcp_service_instance(instance) is False


def test_is_mcp_service_instance_rejects_non_service_instance():
    instance = _instance(
        instance_kind="data",
        domain="mcp",
        config={"provider_kind": "mcp"},
    )

    assert is_mcp_service_instance(instance) is False
