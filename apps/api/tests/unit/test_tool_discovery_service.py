from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.tool_discovery_service import ToolDiscoveryService


@pytest.mark.asyncio
async def test_rescan_scoped_provider_skips_local_and_marks_scoped_stale():
    session = MagicMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar=lambda: True))
    service = ToolDiscoveryService(session=session)
    provider_id = uuid4()
    service._scan_local_tools = AsyncMock(return_value=9)
    service._scan_mcp_providers = AsyncMock(return_value=(3, [provider_id]))
    service._mark_stale = AsyncMock(return_value=2)
    service.session.flush = AsyncMock()

    stats = await service.rescan(include_local=False, provider_instance_id=provider_id)

    service._scan_local_tools.assert_not_called()
    service._scan_mcp_providers.assert_called_once()
    assert service._scan_mcp_providers.call_args.kwargs["provider_instance_id"] == provider_id
    service._mark_stale.assert_called_once()
    assert service._mark_stale.call_args.kwargs["include_local"] is False
    assert service._mark_stale.call_args.kwargs["full_mcp_scan"] is False
    assert service._mark_stale.call_args.kwargs["scanned_provider_ids"] == [provider_id]
    service.session.flush.assert_called_once()
    assert stats["scope"] == "provider"
    assert stats["provider_instance_id"] == str(provider_id)
    assert stats["local_upserted"] == 0
    assert stats["mcp_upserted"] == 3
    assert stats["marked_inactive"] == 2


@pytest.mark.asyncio
async def test_rescan_all_marks_full_mcp_scope():
    session = MagicMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar=lambda: True))
    service = ToolDiscoveryService(session=session)
    service._scan_local_tools = AsyncMock(return_value=4)
    service._scan_mcp_providers = AsyncMock(return_value=(7, [uuid4()]))
    service._mark_stale = AsyncMock(return_value=1)
    service.session.flush = AsyncMock()

    stats = await service.rescan(include_local=True, provider_instance_id=None)

    service._scan_local_tools.assert_called_once()
    service._scan_mcp_providers.assert_called_once()
    assert service._scan_mcp_providers.call_args.kwargs["provider_instance_id"] is None
    service._mark_stale.assert_called_once()
    assert service._mark_stale.call_args.kwargs["include_local"] is True
    assert service._mark_stale.call_args.kwargs["full_mcp_scan"] is True
    assert stats["scope"] == "all"
    assert stats["provider_instance_id"] is None
    assert stats["local_upserted"] == 4
    assert stats["mcp_upserted"] == 7
    assert stats["marked_inactive"] == 1


@pytest.mark.asyncio
async def test_probe_mcp_provider_returns_preview_and_ignores_empty_tool_names():
    service = ToolDiscoveryService(session=MagicMock())
    provider = SimpleNamespace(
        id=uuid4(),
        slug="mcp-jira-prod",
        url="https://mcp.prod.example/api",
    )
    service._get_mcp_provider = AsyncMock(return_value=provider)
    service._fetch_mcp_tools = AsyncMock(
        return_value=[
            {"name": "", "description": "invalid"},
            {
                "name": "jira.issue.get",
                "description": "Get issue",
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
            },
            {
                "name": "jira.issue.create",
                "description": "Create issue",
                "inputSchema": {"type": "object"},
                "outputSchema": None,
            },
        ]
    )

    result = await service.probe_mcp_provider(provider.id)

    assert result["provider_slug"] == "mcp-jira-prod"
    assert result["provider_url"] == "https://mcp.prod.example/api"
    assert result["tools_count"] == 2
    assert result["tools"][0]["slug"] == "jira.issue.get"
    assert result["tools"][0]["has_input_schema"] is True
    assert result["tools"][0]["has_output_schema"] is True
    assert result["tools"][1]["slug"] == "jira.issue.create"
    assert result["tools"][1]["has_output_schema"] is False


@pytest.mark.asyncio
async def test_onboard_mcp_provider_runs_probe_rescan_and_enable():
    service = ToolDiscoveryService(session=MagicMock())
    provider_id = uuid4()
    service.probe_mcp_provider = AsyncMock(return_value={"tools_count": 5})
    service.rescan = AsyncMock(return_value={"mcp_upserted": 5})
    service._set_provider_runtime_publication = AsyncMock(return_value=4)
    service._count_provider_tools = AsyncMock(return_value=(5, 5))

    result = await service.onboard_mcp_provider(
        provider_instance_id=provider_id,
        enable_all_in_runtime=True,
        include_local=False,
    )

    service.probe_mcp_provider.assert_called_once_with(provider_id)
    service.rescan.assert_called_once_with(
        include_local=False,
        provider_instance_id=provider_id,
    )
    service._set_provider_runtime_publication.assert_called_once_with(
        provider_instance_id=provider_id,
        use_in_runtime=True,
    )
    service._count_provider_tools.assert_called_once_with(provider_id)
    assert result["provider_instance_id"] == str(provider_id)
    assert result["probe_tools_count"] == 5
    assert result["enabled_updated"] == 4
    assert result["active_discovered_tools"] == 5
    assert result["runtime_enabled_tools"] == 5


@pytest.mark.asyncio
async def test_onboard_mcp_provider_without_enable_skips_publication_update():
    service = ToolDiscoveryService(session=MagicMock())
    provider_id = uuid4()
    service.probe_mcp_provider = AsyncMock(return_value={"tools_count": 2})
    service.rescan = AsyncMock(return_value={"mcp_upserted": 2})
    service._set_provider_runtime_publication = AsyncMock(return_value=0)
    service._count_provider_tools = AsyncMock(return_value=(2, 1))

    result = await service.onboard_mcp_provider(
        provider_instance_id=provider_id,
        enable_all_in_runtime=False,
        include_local=False,
    )

    service._set_provider_runtime_publication.assert_not_called()
    assert result["enable_all_in_runtime"] is False
    assert result["enabled_updated"] == 0
    assert result["active_discovered_tools"] == 2
    assert result["runtime_enabled_tools"] == 1


@pytest.mark.asyncio
async def test_onboard_mcp_provider_defaults_to_no_runtime_publication():
    service = ToolDiscoveryService(session=MagicMock())
    provider_id = uuid4()
    service.probe_mcp_provider = AsyncMock(return_value={"tools_count": 1})
    service.rescan = AsyncMock(return_value={"mcp_upserted": 1})
    service._set_provider_runtime_publication = AsyncMock(return_value=1)
    service._count_provider_tools = AsyncMock(return_value=(1, 0))

    result = await service.onboard_mcp_provider(
        provider_instance_id=provider_id,
        include_local=False,
    )

    service._set_provider_runtime_publication.assert_not_called()
    assert result["enable_all_in_runtime"] is False
    assert result["enabled_updated"] == 0


@pytest.mark.asyncio
async def test_scan_mcp_providers_does_not_mark_failed_provider_as_scanned():
    service = ToolDiscoveryService(session=MagicMock())
    provider_id = uuid4()
    provider = SimpleNamespace(id=provider_id, slug="mcp-jira-prod", url="https://mcp.prod.example/api")
    service._load_mcp_providers = AsyncMock(return_value=[provider])
    service._fetch_mcp_tools = AsyncMock(side_effect=RuntimeError("mcp offline"))
    service._upsert = AsyncMock()

    total, scanned_ids = await service._scan_mcp_providers(
        now=datetime.now(timezone.utc),
        provider_instance_id=provider_id,
    )

    assert total == 0
    assert scanned_ids == []
    service._upsert.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_mcp_tools_propagates_client_error(monkeypatch):
    async def _boom(**_kwargs):
        raise ValueError("Unable to parse MCP response body")

    monkeypatch.setattr(
        "app.services.tool_discovery_service.mcp_list_tools",
        _boom,
    )
    with pytest.raises(ValueError, match="Unable to parse MCP response body"):
        await ToolDiscoveryService._fetch_mcp_tools("http://mcp")


@pytest.mark.asyncio
async def test_get_mcp_provider_accepts_provider_kind_flag():
    provider_id = uuid4()
    provider = SimpleNamespace(
        id=provider_id,
        slug="gateway-jira",
        instance_kind="service",
        domain="jira",
        config={"provider_kind": "mcp"},
        is_active=True,
        url="https://mcp.example/api",
    )
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = provider

    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result)
    service = ToolDiscoveryService(session=session)

    resolved = await service._get_mcp_provider(provider_id)

    assert resolved.slug == "gateway-jira"


@pytest.mark.asyncio
async def test_load_mcp_providers_filters_non_mcp_services():
    mcp_provider = SimpleNamespace(
        id=uuid4(),
        slug="gateway-mcp",
        instance_kind="service",
        domain="jira",
        config={"provider_kind": "mcp"},
        is_active=True,
        url="https://mcp.example/api",
    )
    non_mcp_provider = SimpleNamespace(
        id=uuid4(),
        slug="gateway-http",
        instance_kind="service",
        domain="jira",
        config={"provider_kind": "http"},
        is_active=True,
        url="https://http.example/api",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [mcp_provider, non_mcp_provider]

    session = MagicMock()
    session.execute = AsyncMock(return_value=execute_result)
    service = ToolDiscoveryService(session=session)

    providers = await service._load_mcp_providers(provider_instance_id=None)

    assert [provider.slug for provider in providers] == ["gateway-mcp"]


@pytest.mark.asyncio
async def test_resolve_mcp_domains_prefers_collection_fk_runtime_domain():
    provider = SimpleNamespace(id=uuid4(), config={})
    collection_id = uuid4()
    data_collection_instance = SimpleNamespace(
        id=collection_id,
        slug="collection-sales",
        domain="rag",
        config={},
    )
    linked_jira = SimpleNamespace(
        id=uuid4(),
        slug="jira-prod",
        domain="jira",
        config={
            "provider_kind": "remote_data",
            "capability_domains": ["jira"],
        },
    )
    linked_instances_result = MagicMock()
    linked_instances_result.scalars.return_value.all.return_value = [data_collection_instance, linked_jira]
    collection_lookup_result = MagicMock()
    collection_lookup_result.scalar_one_or_none.return_value = SimpleNamespace(collection_type="table")
    missing_collection_result = MagicMock()
    missing_collection_result.scalar_one_or_none.return_value = None

    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            linked_instances_result,
            collection_lookup_result,
            missing_collection_result,
        ]
    )
    service = ToolDiscoveryService(session=session)

    domains = await service._resolve_mcp_domains(provider)

    assert domains == ["collection.table", "jira"]
