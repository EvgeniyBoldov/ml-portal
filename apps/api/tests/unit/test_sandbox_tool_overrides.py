from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.tool_resolver import ToolResolver
from app.services.sandbox_override_resolver import SandboxToolOverrides


def _discovered_tool():
    return SimpleNamespace(
        id="discovered-1",
        slug="records.search",
        name="Search records",
        description="Search records",
        domains=["collection.table"],
        input_schema={"type": "object", "properties": {}},
        output_schema=None,
        risk_level="destructive",
    )


@pytest.mark.asyncio
async def test_publication_false_removes_candidate_before_operation_resolution():
    resolver = ToolResolver(session=SimpleNamespace())

    result = await resolver.resolve(
        discovered_tool=_discovered_tool(),
        instance=SimpleNamespace(slug="records"),
        provider=SimpleNamespace(slug="records-provider"),
        runtime_domain="collection.table",
        context_domains=["collection.table"],
        sandbox_tool_overrides=SandboxToolOverrides(publication={"discovered-1": False}),
    )

    assert result is None


@pytest.mark.asyncio
async def test_semantic_overrides_are_applied_without_schema_or_risk_downgrade():
    resolver = ToolResolver(session=SimpleNamespace())

    result = await resolver.resolve(
        discovered_tool=_discovered_tool(),
        instance=SimpleNamespace(slug="records"),
        provider=SimpleNamespace(slug="records-provider"),
        runtime_domain="collection.table",
        context_domains=["collection.table"],
        sandbox_tool_overrides=SandboxToolOverrides(
            semantics={
                "discovered-1": {
                    "title": "Curated search",
                    "description": "Sandbox description",
                    "risk_level": "safe",
                    "side_effects": True,
                    "requires_confirmation": True,
                    "idempotent": False,
                    "credential_scope": "platform",
                    "input_schema": {"type": "string"},
                }
            }
        ),
    )

    assert result is not None
    assert result.title == "Curated search"
    assert result.description == "Sandbox description"
    assert result.risk_level == "destructive"
    assert result.side_effects is True
    assert result.requires_confirmation is True
    assert result.idempotent is False
    assert result.credential_scope == "auto"
    assert result.input_schema == {
        "type": "object",
        "properties": {},
        "x-runtime": {
            "risk_level": "safe",
            "side_effects": False,
            "requires_confirmation": False,
            "credential_scope": "auto",
        },
    }
    assert result.sandbox_override_snapshot["configured"]["risk_level"] == "safe"
    assert result.sandbox_override_snapshot["effective"]["risk_level"] == "destructive"

