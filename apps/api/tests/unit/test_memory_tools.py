from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.builtins import memory as memory_tools
from app.agents.context import ToolContext
from app.services.memory_lookup_service import MemoryLookupService


class _Repository:
    def __init__(self, *, glossary, projects, facts) -> None:
        self.glossary = glossary
        self.projects = projects
        self.facts = facts

    async def list_visible_glossary(self, **_: object):
        return self.glossary

    async def list_active_projects(self, **_: object):
        return self.projects

    async def list_project_facts(self, **_: object):
        return self.facts

    async def read_project_facts(self, *, project_key: str, keys, **_: object):
        project = next((item for item in self.projects if item.key == project_key), None)
        return project, [item for item in self.facts if item.subject in keys]


@pytest.mark.asyncio
async def test_lookup_expands_glossary_alias_then_discovers_project_memory_keys() -> None:
    project_id = uuid4()
    service = MemoryLookupService(_Repository(
        glossary=[SimpleNamespace(
            canonical_term="Немезида", aliases=["Нема", "nema", "nemesis"],
            description="Проектная платформа",
        ), SimpleNamespace(
            canonical_term="domain name system", aliases=["DNS", "днс"],
            description="Система доменных имён",
        )],
        projects=[SimpleNamespace(id=project_id, key="nemesis", name="Немезида", aliases=[])],
        facts=[SimpleNamespace(project_id=project_id, subject="network.dns_servers", kind="rule")],
    ))

    result = await service.lookup(
        terms=["DNS", "Нема"], user_id=uuid4(), tenant_id=uuid4(),
    )

    assert {item["term"] for item in result["glossary"]} == {"Немезида", "domain name system"}
    assert result["projects"] == [{
        "project_key": "nemesis", "name": "Немезида", "keys": [{
            "key": "network.dns_servers", "label": "network dns servers",
            "kind": "rule", "matched_via": ["dns"],
        }],
    }]


@pytest.mark.asyncio
async def test_lookup_reports_multiple_project_matches_without_reading_either() -> None:
    service = MemoryLookupService(_Repository(
        glossary=[],
        projects=[
            SimpleNamespace(id=uuid4(), key="one", name="One", aliases=["shared"]),
            SimpleNamespace(id=uuid4(), key="two", name="Two", aliases=["shared"]),
        ],
        facts=[],
    ))

    result = await service.lookup(terms=["shared"], user_id=uuid4(), tenant_id=uuid4())

    assert result["projects"] == []
    assert {item["project_key"] for item in result["ambiguous_projects"]} == {"one", "two"}


@pytest.mark.asyncio
async def test_lookup_resolves_multiple_distinct_projects_in_one_call() -> None:
    first_id, second_id = uuid4(), uuid4()
    service = MemoryLookupService(_Repository(
        glossary=[],
        projects=[
            SimpleNamespace(id=first_id, key="nemesis", name="Nemesis", aliases=[]),
            SimpleNamespace(id=second_id, key="orion", name="Orion", aliases=[]),
        ],
        facts=[],
    ))

    result = await service.lookup(terms=["Nemesis", "Orion"], user_id=uuid4(), tenant_id=uuid4())

    assert [item["project_key"] for item in result["projects"]] == ["nemesis", "orion"]
    assert result["ambiguous_projects"] == []


@pytest.mark.asyncio
async def test_memory_read_returns_only_requested_keys() -> None:
    project_id = uuid4()
    service = MemoryLookupService(_Repository(
        glossary=[], projects=[SimpleNamespace(id=project_id, key="nemesis", name="Немезида", aliases=[])],
        facts=[SimpleNamespace(
            project_id=project_id, subject="network.dns_servers", value="10.0.0.53",
            kind="rule", confidence=0.9,
        )],
    ))

    result = await service.read(tenant_id=uuid4(), projects=[{
        "project_key": "nemesis", "keys": ["network.dns_servers", "other"],
    }])

    assert result["projects"][0]["entries"][0]["value"] == "10.0.0.53"
    assert result["projects"][0]["missing_keys"] == ["other"]


@pytest.mark.asyncio
async def test_memory_tools_delegate_to_the_memory_service(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Service:
        async def lookup(self, **_: object):
            return {"glossary": [], "expanded_terms": ["DNS"], "projects": [], "ambiguous_projects": [], "project_suggestions": []}

        async def read(self, **_: object):
            return {"projects": []}

    async def _run(_ctx, callback):
        return await callback(_Service())

    monkeypatch.setattr(memory_tools, "_run_with_session", _run)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())

    lookup = await memory_tools.MemoryLookupTool().v1_0_0(ctx, {"terms": ["DNS", "Нема"]})
    read = await memory_tools.MemoryReadTool().v1_0_0(ctx, {"projects": [{"project_key": "nemesis", "keys": ["network.dns_servers"]}]})

    assert lookup.success is True
    assert read.success is True


@pytest.mark.asyncio
async def test_memory_lookup_reports_validation_and_service_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    missing = await memory_tools.MemoryLookupTool().v1_0_0(ctx, {})

    async def _broken(_ctx, _callback):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(memory_tools, "_run_with_session", _broken)
    failed = await memory_tools.MemoryLookupTool().v1_0_0(ctx, {"terms": ["DNS"]})

    assert missing.success is False
    assert failed.success is False
    assert failed.error == "Memory lookup is temporarily unavailable"


def test_memory_mark_is_a_system_memory_operation() -> None:
    tool = memory_tools.MemoryMarkTool()

    assert tool.tool_slug == "memory.mark"
    assert "system" in tool.domains
    assert tool.get_version("1.0.0") is not None
