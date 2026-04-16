from types import SimpleNamespace
from uuid import uuid4

from app.agents.contracts import ProviderExecutionTarget, ResolvedDataInstance, ResolvedOperation
from app.agents.operation_router import OperationResolveResult
from app.services.permission_service import EffectivePermissions
from app.services.runtime_capability_graph_service import (
    CollectionGraphInfo,
    RuntimeCapabilityGraphService,
)


def _resolved_fixture() -> OperationResolveResult:
    collection_id = str(uuid4())
    data = ResolvedDataInstance(
        instance_id=str(uuid4()),
        slug="vendors-data",
        name="Vendors Data",
        domain="collection.table",
        collection_id=collection_id,
        collection_slug="vendors",
        placement="local",
        provider_instance_slug="local-service",
    )
    target = ProviderExecutionTarget(
        operation_slug="vendors-data.collection.table.list_rows",
        provider_type="local",
        provider_instance_slug="local-service",
        data_instance_id=data.instance_id,
        data_instance_slug=data.slug,
    )
    operation = ResolvedOperation(
        operation_slug=target.operation_slug,
        operation="collection.table.list_rows",
        name="List rows",
        description="List table rows",
        input_schema={},
        data_instance_id=data.instance_id,
        data_instance_slug=data.slug,
        source="local",
        risk_level="low",
        side_effects="none",
        target=target,
    )
    result = OperationResolveResult(effective_permissions=EffectivePermissions())
    result.resolved_data_instances = [data]
    result.resolved_operations = [operation]
    return result


def test_capability_graph_links_agent_operation_data_collection_provider():
    resolved = _resolved_fixture()
    collection_id = resolved.resolved_data_instances[0].collection_id
    agents = [
        SimpleNamespace(
            slug="ops-agent",
            name="Ops Agent",
            current_version_id=uuid4(),
            allowed_collection_ids=[collection_id],
        )
    ]
    collections = {
        collection_id: CollectionGraphInfo(
            id=collection_id,
            slug="vendors",
            name="Vendors",
            collection_type="table",
        ),
        "vendors": CollectionGraphInfo(
            id=collection_id,
            slug="vendors",
            name="Vendors",
            collection_type="table",
        ),
    }

    graph = RuntimeCapabilityGraphService().build(
        resolved=resolved,
        agents=agents,
        collections=collections,
    )

    node_types = {node["type"] for node in graph["nodes"]}
    assert {"agent", "operation", "data_instance", "collection", "provider_instance"} <= node_types
    assert any(edge["type"] == "can_call" for edge in graph["edges"])
    assert graph["stats"]["operations"] == 1


def test_capability_graph_respects_agent_collection_binding_filter():
    resolved = _resolved_fixture()
    agents = [
        SimpleNamespace(
            slug="restricted-agent",
            name="Restricted Agent",
            current_version_id=uuid4(),
            allowed_collection_ids=[str(uuid4())],
        )
    ]

    graph = RuntimeCapabilityGraphService().build(
        resolved=resolved,
        agents=agents,
        collections={},
    )

    assert any(node["type"] == "agent" for node in graph["nodes"])
    assert not any(edge["type"] == "can_call" for edge in graph["edges"])
