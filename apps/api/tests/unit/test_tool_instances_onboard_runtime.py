from __future__ import annotations

from uuid import uuid4

from app.api.v1.routers.admin.tool_instances import _aggregate_linked_runtime
from app.schemas.tool_instances import LinkedDataInstanceRuntimeSummary


def test_aggregate_linked_runtime_counts_ready_and_operations():
    items = [
        LinkedDataInstanceRuntimeSummary(
            instance_id=uuid4(),
            slug="jira-prod",
            domain="jira",
            is_runtime_ready=True,
            runtime_readiness_reason="ready",
            semantic_source="active_profile",
            discovered_tools_count=12,
            runtime_operations_count=11,
        ),
        LinkedDataInstanceRuntimeSummary(
            instance_id=uuid4(),
            slug="jira-stage",
            domain="jira",
            is_runtime_ready=False,
            runtime_readiness_reason="missing_active_semantic_profile",
            semantic_source="none",
            discovered_tools_count=12,
            runtime_operations_count=0,
        ),
    ]

    ready, not_ready, ops_total = _aggregate_linked_runtime(items)

    assert ready == 1
    assert not_ready == 1
    assert ops_total == 11
