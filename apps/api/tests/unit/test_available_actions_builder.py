from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.agents.available_actions import AvailableActionsBuilder, _normalize_risk
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation


@pytest.mark.asyncio
async def test_available_actions_keeps_destructive_operations_without_env_hardcode():
    builder = AvailableActionsBuilder(session=MagicMock())
    agent = SimpleNamespace(slug="analyst", description="Data analyst", tags=["data"])
    target = ProviderExecutionTarget(
        operation_slug="instance.jira-prod.jira.issue.delete",
        provider_type="mcp",
        provider_instance_id="provider-1",
        provider_instance_slug="mcp-jira",
        provider_url="https://mcp.example.local",
        data_instance_id="instance-1",
        data_instance_slug="jira-prod",
        mcp_tool_name="jira.issue.delete",
        has_credentials=True,
    )
    operation = ResolvedOperation(
        operation_slug="instance.jira-prod.jira.issue.delete",
        operation="jira.issue.delete",
        name="Delete issue",
        description="Dangerous op",
        input_schema={},
        data_instance_id="instance-1",
        data_instance_slug="jira-prod",
        provider_instance_id="provider-1",
        provider_instance_slug="mcp-jira",
        source="mcp",
        risk_level="destructive",
        side_effects=True,
        idempotent=False,
        requires_confirmation=True,
        target=target,
    )

    actions = await builder.build(
        agent=agent,
        agent_version=None,
        resolved_operations=[operation],
        routable_agents=None,
    )

    assert len(actions.operations) == 1
    assert actions.operations[0].operation_slug == "instance.jira-prod.jira.issue.delete"
    assert actions.operations[0].risk_level == "destructive"


def test_normalize_risk_defaults_to_safe_for_unknown_values():
    assert _normalize_risk(None) == "safe"
    assert _normalize_risk("critical") == "safe"
    assert _normalize_risk(" destructive ") == "destructive"
