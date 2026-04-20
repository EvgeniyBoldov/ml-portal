from __future__ import annotations

from types import SimpleNamespace

from app.agents.contracts import (
    ProviderExecutionTarget,
    ResolvedDataInstance,
    ResolvedOperation,
)
from app.agents.preflight_policy import apply_operation_policy_filter
from app.agents.runtime_graph import (
    OperationExecutionBinding,
    OperationRuntimeContext,
    RuntimeExecutionGraph,
)


def _resolved_operation(
    *,
    operation_slug: str,
    data_instance_slug: str,
    side_effects: str,
) -> ResolvedOperation:
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="local",
        data_instance_id="data-1",
        data_instance_slug=data_instance_slug,
        handler_slug="collection.search",
    )
    return ResolvedOperation(
        operation_slug=operation_slug,
        operation=operation_slug.split(".")[-1],
        name=operation_slug,
        data_instance_id="data-1",
        data_instance_slug=data_instance_slug,
        source="local",
        side_effects=side_effects,
        target=target,
    )


def _execution_graph(operations: list[ResolvedOperation]) -> RuntimeExecutionGraph:
    bindings = {}
    for operation in operations:
        bindings[operation.operation_slug] = OperationExecutionBinding(
            operation_slug=operation.operation_slug,
            target=operation.target,
            context=OperationRuntimeContext(
                instance_id=operation.data_instance_id,
                instance_slug=operation.data_instance_slug,
                provider_instance_id=operation.provider_instance_id or operation.data_instance_id,
                provider_instance_slug=operation.provider_instance_slug or operation.data_instance_slug,
                has_credentials=False,
                credential_scope=operation.credential_scope,
                config={},
                provider_config={},
                domain="collection.document",
            ),
            credential=None,
        )
    return RuntimeExecutionGraph(bindings=bindings)


def test_preflight_policy_filters_write_and_destructive_operations():
    safe_op = _resolved_operation(
        operation_slug="instance.docs.get",
        data_instance_slug="docs",
        side_effects="none",
    )
    write_op = _resolved_operation(
        operation_slug="instance.docs.update",
        data_instance_slug="docs",
        side_effects="write",
    )
    destructive_op = _resolved_operation(
        operation_slug="instance.docs.delete",
        data_instance_slug="docs",
        side_effects="destructive",
    )

    op_result = SimpleNamespace(
        resolved_operations=[safe_op, write_op, destructive_op],
        execution_graph=_execution_graph([safe_op, write_op, destructive_op]),
        resolved_data_instances=[
            ResolvedDataInstance(
                instance_id="data-1",
                slug="docs",
                name="Docs",
                domain="collection.document",
                placement="local",
                semantic_source="derived_collection",
            )
        ],
    )

    filtered = apply_operation_policy_filter(
        operation_result=op_result,
        platform_config={"forbid_write_in_prod": True},
    )

    assert filtered == {"instance.docs.update", "instance.docs.delete"}
    assert [op.operation_slug for op in op_result.resolved_operations] == ["instance.docs.get"]
    assert set(op_result.execution_graph.bindings.keys()) == {"instance.docs.get"}


def test_preflight_policy_ignores_removed_derived_semantic_toggle():
    derived_op = _resolved_operation(
        operation_slug="instance.collection_table.search",
        data_instance_slug="collection-table",
        side_effects="none",
    )
    active_op = _resolved_operation(
        operation_slug="instance.jira.search",
        data_instance_slug="jira-prod",
        side_effects="none",
    )

    op_result = SimpleNamespace(
        resolved_operations=[derived_op, active_op],
        execution_graph=_execution_graph([derived_op, active_op]),
        resolved_data_instances=[
            ResolvedDataInstance(
                instance_id="data-1",
                slug="collection-table",
                name="Collection Table",
                domain="collection.table",
                placement="local",
                semantic_source="derived_collection",
            ),
            ResolvedDataInstance(
                instance_id="data-2",
                slug="jira-prod",
                name="Jira Prod",
                domain="jira",
                placement="remote",
                semantic_source="active_profile",
            ),
        ],
    )

    filtered = apply_operation_policy_filter(
        operation_result=op_result,
        platform_config={"allow_derived_semantic_operations": False},
    )

    assert filtered == set()
    assert [op.operation_slug for op in op_result.resolved_operations] == [
        "instance.collection_table.search",
        "instance.jira.search",
    ]


def test_preflight_policy_filters_high_risk_when_forbidden():
    safe_op = _resolved_operation(
        operation_slug="instance.docs.get",
        data_instance_slug="docs",
        side_effects="none",
    )
    high_risk_op = _resolved_operation(
        operation_slug="instance.docs.delete",
        data_instance_slug="docs",
        side_effects="destructive",
    )
    high_risk_op.risk_level = "high"
    safe_op.risk_level = "low"

    op_result = SimpleNamespace(
        resolved_operations=[safe_op, high_risk_op],
        execution_graph=_execution_graph([safe_op, high_risk_op]),
        resolved_data_instances=[
            ResolvedDataInstance(
                instance_id="data-1",
                slug="docs",
                name="Docs",
                domain="collection.document",
                placement="local",
                semantic_source="derived_collection",
            )
        ],
    )

    filtered = apply_operation_policy_filter(
        operation_result=op_result,
        platform_config={"forbid_high_risk": True},
    )

    assert filtered == {"instance.docs.delete"}
    assert [op.operation_slug for op in op_result.resolved_operations] == ["instance.docs.get"]
