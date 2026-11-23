"""Unit tests for AgentService (versioned agents business logic).

Replaces repositories with AsyncMock after construction and patches the
RBAC collaborators in the service namespace. Covers slug normalization,
container CRUD, version workflow (create/inherit/update/delete/publish/
archive/set-current) and runtime resolution/planner catalogue contracts.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AgentVersionNotFoundError,
    AgentVersionNotEditableError,
    AppError as AgentError,
)
from app.models.agent import Agent, AgentType
from app.models.agent_version import AgentVersion, AgentVersionStatus
from app.services.agent_service import (
    LEGACY_AGENT_SLUG_ALIASES,
    AgentService,
)

AGENT_ID = uuid4()
VERSION_ID = uuid4()


def make_agent(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(
        id=AGENT_ID,
        slug="researcher",
        name="Researcher",
        description="agent description",
        tags=["research"],
        agent_type=AgentType.REGULAR.value,
        lifecycle_status="active",
        current_version_id=VERSION_ID,
        logging_level="brief",
        model="gpt-x",
        temperature=0.2,
        requires_confirmation_for_write=False,
        risk_level="low",
        allow_all_collections=False,
        allowed_collection_ids=[],
        provides_keys=["report"],
        deprecated_at=None,
        retention_days=14,
        created_at="2026-01-01",
        updated_at="2026-01-01",
        versions=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_version(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(
        id=VERSION_ID,
        agent_id=AGENT_ID,
        version=2,
        status=AgentVersionStatus.PUBLISHED.value,
        identity="identity",
        mission="mission",
        scope="scope",
        rules="rules",
        tool_use_rules="tool rules",
        output_format="format",
        examples="examples",
        short_info="short",
        never_do="never",
        allowed_ops="ops",
        notes="notes",
        task_contracts=None,
        supports_dynamic_contracts=True,
        requires_fresh_retrieval=False,
        created_at="2026-01-01",
        updated_at="2026-01-01",
    )
    base.update(overrides)
    version = SimpleNamespace(**base)
    version.is_editable = version.status == AgentVersionStatus.DRAFT.value
    version.can_publish = version.status == AgentVersionStatus.DRAFT.value
    version.can_archive = version.status == AgentVersionStatus.PUBLISHED.value
    return version


def make_service() -> AgentService:
    svc = AgentService(MagicMock())
    svc.agent_repo = AsyncMock()
    svc.version_repo = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# Slug normalization
# ---------------------------------------------------------------------------


def test_normalize_agent_slug_maps_legacy_alias():
    svc = make_service()
    assert svc._normalize_agent_slug("rag-search") == "knowledge-base-search"
    assert svc._normalize_agent_slug("other") == "other"
    assert svc._normalize_agent_slug(None) is None


def test_legacy_alias_table_contents():
    assert LEGACY_AGENT_SLUG_ALIASES == {"rag-search": "knowledge-base-search"}


# ---------------------------------------------------------------------------
# Agent container
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_duplicate_slug_rejected():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = make_agent()
    with pytest.raises(AgentAlreadyExistsError, match="'researcher' already exists"):
        await svc.create_agent(slug="researcher", name="Researcher")


@pytest.mark.asyncio
async def test_create_agent_creates_and_ensures_platform_deny():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = None
    svc.agent_repo.create.side_effect = lambda agent: agent
    with patch("app.services.agent_service.RbacService") as rbac_cls:
        rbac_cls.return_value.ensure_platform_deny = AsyncMock()
        agent = await svc.create_agent(
            slug="writer",
            name="Writer",
            allow_all_collections=1,
            tags=["t"],
        )
    assert agent.slug == "writer"
    assert agent.allow_all_collections is True
    assert agent.agent_type == AgentType.REGULAR
    created = svc.agent_repo.create.await_args.args[0]
    assert created.slug == "writer"
    rbac_cls.return_value.ensure_platform_deny.assert_awaited_once_with(
        "agent", agent.id
    )


@pytest.mark.asyncio
async def test_get_agent_missing_or_deprecated_raises():
    svc = make_service()
    svc.agent_repo.get_by_id.return_value = None
    with pytest.raises(AgentNotFoundError, match=str(AGENT_ID)):
        await svc.get_agent(AGENT_ID)
    svc.agent_repo.get_by_id.return_value = make_agent(lifecycle_status="deprecated")
    with pytest.raises(AgentNotFoundError):
        await svc.get_agent(AGENT_ID)


@pytest.mark.asyncio
async def test_get_agent_by_slug_retries_with_raw_slug_for_alias():
    svc = make_service()
    svc.agent_repo.get_by_slug.side_effect = [None, make_agent()]
    agent = await svc.get_agent_by_slug("rag-search")
    assert agent.slug == "researcher"
    assert svc.agent_repo.get_by_slug.await_count == 2
    svc.agent_repo.get_by_slug.assert_any_await("knowledge-base-search")
    svc.agent_repo.get_by_slug.assert_any_await("rag-search")


@pytest.mark.asyncio
async def test_get_agent_by_slug_missing_raises():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = None
    with pytest.raises(AgentNotFoundError, match="Agent 'researcher' not found"):
        await svc.get_agent_by_slug("researcher")


@pytest.mark.asyncio
async def test_get_agent_by_slug_deprecated_raises():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = make_agent(lifecycle_status="deprecated")
    with pytest.raises(AgentNotFoundError):
        await svc.get_agent_by_slug("researcher")


@pytest.mark.asyncio
async def test_get_agent_with_versions_missing_raises():
    svc = make_service()
    svc.agent_repo.get_by_id_with_versions.return_value = None
    with pytest.raises(AgentNotFoundError):
        await svc.get_agent_with_versions_by_id(AGENT_ID)


@pytest.mark.asyncio
async def test_get_agent_detail_shapes_versions_with_defaults():
    version = make_version(task_contracts=None, notes=None)
    svc = make_service()
    svc.agent_repo.get_by_id_with_versions.return_value = make_agent(versions=[version])
    detail = await svc.get_agent_detail(AGENT_ID)
    assert detail["slug"] == "researcher"
    assert detail["retention_days"] == 14
    assert detail["lifecycle_status"] == "active"
    assert detail["deprecated_at"] is None
    assert len(detail["versions"]) == 1
    version_info = detail["versions"][0]
    assert version_info["id"] == VERSION_ID
    assert version_info["task_contracts"] == []
    assert version_info["supports_dynamic_contracts"] is True
    assert version_info["requires_fresh_retrieval"] is False
    assert version_info["notes"] is None
    assert version_info["mission"] == "mission"


@pytest.mark.asyncio
async def test_update_agent_without_fields_returns_agent_untouched():
    svc = make_service()
    agent = make_agent()
    svc.agent_repo.get_by_id.return_value = agent
    result = await svc.update_agent(AGENT_ID)
    assert result is agent
    svc.agent_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_agent_applies_only_provided_fields():
    svc = make_service()
    svc.agent_repo.get_by_id.return_value = make_agent()
    svc.agent_repo.update.side_effect = lambda agent, data: SimpleNamespace(
        **{**agent.__dict__, **data}
    )
    await svc.update_agent(AGENT_ID, name="New", allow_all_collections=1)
    svc.agent_repo.update.assert_awaited_once()
    agent_arg, data_arg = svc.agent_repo.update.await_args.args
    assert data_arg == {"name": "New", "allow_all_collections": True}


@pytest.mark.asyncio
async def test_delete_agent_cleans_rbac_then_deletes():
    svc = make_service()
    svc.agent_repo.get_by_id.return_value = make_agent()
    with patch("app.services.agent_service.RbacCleanupService") as cleanup_cls:
        cleanup_cls.return_value.remove_rules_for_resource = AsyncMock()
        await svc.delete_agent(AGENT_ID)
    cleanup_cls.return_value.remove_rules_for_resource.assert_awaited_once_with(
        resource_type="agent", resource_id=AGENT_ID
    )
    svc.agent_repo.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_agents_delegates_to_repository():
    svc = make_service()
    svc.agent_repo.list_agents.return_value = ([make_agent()], 1)
    agents, total = await svc.list_agents(skip=5, limit=10, include_deprecated=True)
    assert total == 1
    svc.agent_repo.list_agents.assert_awaited_once_with(
        5, 10, include_deprecated=True
    )


# ---------------------------------------------------------------------------
# Version lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_version_resolves_agent_by_slug():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = make_agent()
    svc.version_repo.get_next_version.return_value = 3
    svc.version_repo.create.side_effect = lambda version: version
    version = await svc.create_version("researcher", {"mission": "m"})
    assert version.agent_id == AGENT_ID
    assert version.version == 3
    assert version.status == AgentVersionStatus.DRAFT.value


@pytest.mark.asyncio
async def test_create_version_inherits_from_parent_of_same_agent():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = make_agent()
    svc.version_repo.get_next_version.return_value = 4
    svc.version_repo.get_by_id.return_value = make_version(
        identity="parent identity",
        mission="parent mission",
        notes="parent notes",
        short_info=None,
    )
    svc.version_repo.create.side_effect = lambda version: version
    version = await svc.create_version(
        "researcher",
        {"mission": "new mission", "notes": "new notes"},
        parent_version_id=VERSION_ID,
    )
    assert version.identity == "parent identity"  # inherited
    assert version.mission == "new mission"  # explicit override
    assert version.notes == "new notes"  # notes are never inherited
    assert not hasattr(version, "short_info") or version.short_info is None


@pytest.mark.asyncio
async def test_create_version_ignores_parent_from_other_agent():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = make_agent()
    svc.version_repo.get_next_version.return_value = 2
    svc.version_repo.get_by_id.return_value = make_version(
        agent_id=uuid4(), identity="foreign"
    )
    svc.version_repo.create.side_effect = lambda version: version
    version = await svc.create_version(
        "researcher", {"mission": "m"}, parent_version_id=VERSION_ID
    )
    assert not hasattr(version, "identity") or version.identity is None


@pytest.mark.asyncio
async def test_update_version_rejects_non_draft():
    svc = make_service()
    svc.version_repo.get_by_id.return_value = make_version(
        status=AgentVersionStatus.PUBLISHED.value
    )
    with pytest.raises(AgentVersionNotEditableError, match="not editable"):
        await svc.update_version(VERSION_ID, {"mission": "x"})


@pytest.mark.asyncio
async def test_update_version_filters_fields_and_skips_nones():
    svc = make_service()
    draft = make_version(status=AgentVersionStatus.DRAFT.value)
    svc.version_repo.get_by_id.return_value = draft
    svc.version_repo.update.side_effect = lambda version, data: SimpleNamespace(
        **{**version.__dict__, **data}
    )
    result = await svc.update_version(
        VERSION_ID, {"mission": "m", "notes": None, "unknown": "x"}
    )
    svc.version_repo.update.assert_awaited_once()
    _, data_arg = svc.version_repo.update.await_args.args
    assert data_arg == {"mission": "m"}
    assert result.mission == "m"


@pytest.mark.asyncio
async def test_update_version_without_changes_returns_version():
    svc = make_service()
    draft = make_version(status=AgentVersionStatus.DRAFT.value)
    svc.version_repo.get_by_id.return_value = draft
    result = await svc.update_version(VERSION_ID, {})
    assert result is draft
    svc.version_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_version_rejects_draft():
    svc = make_service()
    svc.version_repo.get_by_id.return_value = make_version(
        status=AgentVersionStatus.DRAFT.value
    )
    with pytest.raises(AgentError, match="Only published or archived"):
        await svc.delete_version(VERSION_ID)


@pytest.mark.asyncio
async def test_delete_version_rejects_current_version():
    svc = make_service()
    svc.version_repo.get_by_id.return_value = make_version(
        status=AgentVersionStatus.PUBLISHED.value
    )
    svc.agent_repo.get_by_id.return_value = make_agent(current_version_id=VERSION_ID)
    with pytest.raises(AgentError, match="Cannot delete current version"):
        await svc.delete_version(VERSION_ID)
    svc.version_repo.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [AgentVersionStatus.PUBLISHED.value, AgentVersionStatus.ARCHIVED.value])
async def test_delete_version_removes_non_current(status):
    svc = make_service()
    svc.version_repo.get_by_id.return_value = make_version(status=status)
    svc.agent_repo.get_by_id.return_value = make_agent(current_version_id=None)
    await svc.delete_version(VERSION_ID)
    svc.version_repo.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_version_requires_draft():
    svc = make_service()
    svc.version_repo.get_by_id.return_value = make_version(
        status=AgentVersionStatus.PUBLISHED.value
    )
    with pytest.raises(AgentError, match="cannot be published"):
        await svc.publish_version(VERSION_ID)


@pytest.mark.asyncio
async def test_publish_version_updates_status_and_refreshes():
    svc = make_service()
    published = make_version(status=AgentVersionStatus.PUBLISHED.value)
    svc.version_repo.get_by_id.side_effect = [
        make_version(status=AgentVersionStatus.DRAFT.value),
        published,
    ]
    result = await svc.publish_version(VERSION_ID)
    assert result is published
    svc.version_repo.update_status.assert_awaited_once_with(
        VERSION_ID, AgentVersionStatus.PUBLISHED.value
    )


@pytest.mark.asyncio
async def test_archive_version_requires_published():
    svc = make_service()
    svc.version_repo.get_by_id.return_value = make_version(
        status=AgentVersionStatus.DRAFT.value
    )
    with pytest.raises(AgentError, match="cannot be archived"):
        await svc.archive_version(VERSION_ID)


@pytest.mark.asyncio
async def test_archive_version_unbinds_current():
    svc = make_service()
    archived = make_version(status=AgentVersionStatus.ARCHIVED.value)
    svc.version_repo.get_by_id.side_effect = [
        make_version(status=AgentVersionStatus.PUBLISHED.value),
        archived,
    ]
    svc.agent_repo.get_by_id.return_value = make_agent(current_version_id=VERSION_ID)
    result = await svc.archive_version(VERSION_ID)
    assert result is archived
    svc.agent_repo.update.assert_awaited_once()
    _, data_arg = svc.agent_repo.update.await_args.args
    assert data_arg == {"current_version_id": None}


@pytest.mark.asyncio
async def test_archive_version_keeps_current_when_other_version():
    svc = make_service()
    other = uuid4()
    svc.version_repo.get_by_id.side_effect = [
        make_version(status=AgentVersionStatus.PUBLISHED.value),
        make_version(status=AgentVersionStatus.ARCHIVED.value),
    ]
    svc.agent_repo.get_by_id.return_value = make_agent(current_version_id=other)
    await svc.archive_version(VERSION_ID)
    svc.agent_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_current_version_rejects_foreign_version():
    svc = make_service()
    svc.agent_repo.get_by_id.return_value = make_agent()
    svc.version_repo.get_by_id.return_value = make_version(agent_id=uuid4())
    with pytest.raises(AgentError, match="does not belong"):
        await svc.set_current_version(AGENT_ID, VERSION_ID)


@pytest.mark.asyncio
async def test_set_current_version_requires_published():
    svc = make_service()
    svc.agent_repo.get_by_id.return_value = make_agent()
    svc.version_repo.get_by_id.return_value = make_version(
        status=AgentVersionStatus.DRAFT.value
    )
    with pytest.raises(AgentError, match="must be published"):
        await svc.set_current_version(AGENT_ID, VERSION_ID)


@pytest.mark.asyncio
async def test_set_current_version_updates_and_returns_detail():
    svc = make_service()
    svc.agent_repo.get_by_id.return_value = make_agent()
    svc.version_repo.get_by_id.return_value = make_version()
    svc.agent_repo.get_by_id_with_versions.return_value = make_agent(versions=[])
    detail = await svc.set_current_version(AGENT_ID, VERSION_ID)
    svc.agent_repo.update.assert_awaited_once()
    _, data_arg = svc.agent_repo.update.await_args.args
    assert data_arg == {"current_version_id": VERSION_ID}
    assert detail["slug"] == "researcher"


@pytest.mark.asyncio
async def test_get_version_missing_raises():
    svc = make_service()
    svc.version_repo.get_by_id.return_value = None
    with pytest.raises(AgentVersionNotFoundError, match=str(VERSION_ID)):
        await svc.get_version(VERSION_ID)


@pytest.mark.asyncio
async def test_get_version_by_number_missing_raises():
    svc = make_service()
    svc.version_repo.get_by_agent_and_version.return_value = None
    with pytest.raises(AgentVersionNotFoundError, match="Version 2 not found"):
        await svc.get_version_by_number_and_agent_id(AGENT_ID, 2)


@pytest.mark.asyncio
async def test_list_versions_resolves_agent_then_delegates():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = make_agent()
    svc.version_repo.get_all_by_agent.return_value = []
    await svc.list_versions("researcher", status_filter="published")
    svc.version_repo.get_all_by_agent.assert_awaited_once_with(
        AGENT_ID, "published"
    )


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------


def planner_service(rows: list) -> AgentService:
    svc = make_service()
    result = MagicMock()
    result.all.return_value = rows
    svc.session = MagicMock()
    svc.session.execute = AsyncMock(return_value=result)
    return svc


@pytest.mark.asyncio
async def test_list_routable_agents_for_planner_prefers_current_version():
    v_current = make_version(id=uuid4(), short_info="current short")
    v_other = make_version(id=uuid4(), short_info="other short")
    agent = make_agent(current_version_id=v_current.id)
    svc = planner_service([(agent, v_other), (agent, v_current)])
    items = await svc.list_routable_agents_for_planner()
    assert len(items) == 1
    assert items[0]["description"] == "current short"


@pytest.mark.asyncio
async def test_list_routable_agents_for_planner_falls_back_to_min_version_id():
    v_low = make_version(id="00000000-0000-0000-0000-000000000001")
    v_high = make_version(id="00000000-0000-0000-0000-000000000002")
    agent = make_agent(current_version_id=uuid4())  # points elsewhere
    svc = planner_service([(agent, v_high), (agent, v_low)])
    items = await svc.list_routable_agents_for_planner()
    # v_low wins via deterministic min-id fallback
    assert items[0]["description"] == "short"


@pytest.mark.asyncio
async def test_list_routable_agents_for_planner_description_priority():
    agent = make_agent(description="agent description")
    cases = [
        (make_version(short_info="  short  ", mission="mission"), "short"),
        (make_version(short_info="", mission=" mission "), "mission"),
        (make_version(short_info=None, mission=None), "agent description"),
    ]
    for version, expected in cases:
        svc = planner_service([(agent, version)])
        items = await svc.list_routable_agents_for_planner()
        assert items[0]["description"] == expected


@pytest.mark.asyncio
async def test_list_routable_agents_for_planner_skips_blank_slug_and_sorts():
    agent_a = make_agent(slug="alpha")
    agent_b = make_agent(slug="beta")
    blank = make_agent(slug="   ")
    svc = planner_service([(agent_b, make_version()), (blank, make_version()), (agent_a, make_version())])
    items = await svc.list_routable_agents_for_planner()
    assert [item["slug"] for item in items] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_list_routable_agents_for_planner_normalizes_meta_fields():
    agent = make_agent(tags=None, provides_keys=None)
    version = make_version(
        task_contracts=None, supports_dynamic_contracts=None, requires_fresh_retrieval=None
    )
    svc = planner_service([(agent, version)])
    item = (await svc.list_routable_agents_for_planner())[0]
    assert item["tags"] == []
    assert item["provides_keys"] == []
    assert item["task_contracts"] == []
    assert item["supports_dynamic_contracts"] is False  # bool(None) after explicit None
    assert item["requires_fresh_retrieval"] is False


@pytest.mark.asyncio
async def test_list_routable_agents_returns_unique_scalars():
    svc = make_service()
    agent = make_agent()
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = [agent]
    svc.session = MagicMock()
    svc.session.execute = AsyncMock(return_value=result)
    assert await svc.list_routable_agents() == [agent]


# ---------------------------------------------------------------------------
# resolve_published_version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_published_version_requires_slug():
    svc = make_service()
    with pytest.raises(AgentNotFoundError, match="agent_slug_required"):
        await svc.resolve_published_version(agent_slug=None)


@pytest.mark.asyncio
async def test_resolve_published_version_normalizes_legacy_alias():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = None
    with pytest.raises(AgentNotFoundError, match="knowledge-base-search"):
        await svc.resolve_published_version(agent_slug="rag-search")
    svc.agent_repo.get_by_slug.assert_awaited_once_with("knowledge-base-search")


@pytest.mark.asyncio
async def test_resolve_published_version_unknown_agent_raises():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = None
    with pytest.raises(AgentNotFoundError, match="Agent 'researcher' not found"):
        await svc.resolve_published_version(agent_slug="researcher", tenant_id=uuid4())


@pytest.mark.asyncio
async def test_resolve_published_version_prefers_current_version():
    svc = make_service()
    current = make_version()
    svc.agent_repo.get_by_slug.return_value = make_agent(current_version_id=VERSION_ID)
    svc.version_repo.get_by_id.return_value = current
    assert await svc.resolve_published_version("researcher") is current
    svc.version_repo.get_published_by_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_published_version_falls_back_when_current_missing():
    svc = make_service()
    published = make_version()
    svc.agent_repo.get_by_slug.return_value = make_agent(current_version_id=VERSION_ID)
    svc.version_repo.get_by_id.return_value = None
    svc.version_repo.get_published_by_agent.return_value = published
    assert await svc.resolve_published_version("researcher") is published


@pytest.mark.asyncio
async def test_resolve_published_version_nothing_published_raises():
    svc = make_service()
    svc.agent_repo.get_by_slug.return_value = make_agent(current_version_id=None)
    svc.version_repo.get_published_by_agent.return_value = None
    with pytest.raises(AgentVersionNotFoundError, match="No published version for agent 'researcher'"):
        await svc.resolve_published_version("researcher")
