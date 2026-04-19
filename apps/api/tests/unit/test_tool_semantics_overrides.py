from __future__ import annotations

from app.agents.tool_semantics import build_tool_semantics


def test_discovered_semantic_override_wins_over_instance_provider_config():
    semantics = build_tool_semantics(
        slug="jira.issue.update",
        source="mcp",
        discovered_name="jira.issue.update",
        discovered_description=None,
        input_schema={"type": "object", "properties": {}},
        domains=["jira"],
        instance_slug="jira-prod",
        instance_domain="jira",
        instance_config={
            "tool_semantics": {
                "jira.issue.update": {
                    "title": "Instance override title",
                    "side_effects": "write",
                }
            }
        },
        provider_config={
            "tool_semantics": {
                "jira.issue.update": {
                    "title": "Provider override title",
                    "side_effects": "destructive",
                }
            }
        },
        draft_semantic_overrides={
            "title": "Discovered override title",
            "side_effects": "none",
            "risk_level": "low",
            "requires_confirmation": False,
        },
    )

    assert semantics.quality == "curated"
    assert semantics.title == "Discovered override title"
    assert semantics.side_effects == "none"
    assert semantics.risk_level == "low"
    assert semantics.requires_confirmation is False


def test_discovered_semantic_override_can_set_examples_and_flags():
    semantics = build_tool_semantics(
        slug="collection.search",
        source="local",
        discovered_name="collection.search",
        discovered_description=None,
        input_schema={"type": "object", "properties": {}},
        domains=["collection.table"],
        instance_slug="collection-tickets",
        instance_domain="collection.table",
        instance_config={},
        provider_config={},
        draft_semantic_overrides={
            "risk_flags": ["tenant_sensitive", "audit_required"],
            "semantic_profile": {"examples": ["Search urgent"]},
        },
    )

    assert semantics.quality == "curated"
    assert semantics.risk_flags == ["tenant_sensitive", "audit_required"]
    assert semantics.examples == ["Search urgent"]
