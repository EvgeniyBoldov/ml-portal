from app.agents.context import ToolResult
from app.agents.runtime.tools import OperationExecutionFacade


def test_collection_info_context_projection_keeps_next_operation_contract():
    result = ToolResult.ok(
        {
            "collection": {
                "id": "collection-id",
                "slug": "template",
                "name": "Templates",
                "type": "template",
                "description": "Template library",
                "usage_rules": "Find a template, inspect its schema, then fill it.",
                "storage_uri": "must-not-enter-context",
            },
            "readiness": {
                "status": "ready",
                "schema_freshness": "fresh",
                "operations_count": 2,
                "provider_health": ["healthy"],
            },
            "tools": [
                {
                    "tool_name": "collection.template.list",
                    "invoke_as": "instance.template.list",
                    "description": "List templates",
                    "arguments": ["limit: integer"],
                    "schema": {"a": "large inspection-only schema"},
                }
            ],
            "contracts": {"workflow": ["type-derived guidance"]},
            "schema": {"fields": [{"name": "large inspection-only field list"}]},
        }
    )

    context = OperationExecutionFacade.format_result_for_context(
        result,
        operation_slug="instance.local-template-tools.collection.info",
    )

    assert "collection.template.list" in context
    assert "instance.template.list" in context
    assert "Find a template, inspect its schema, then fill it." in context
    assert "type-derived guidance" not in context
    assert "must-not-enter-context" not in context
    assert "large inspection-only field list" not in context
    assert "inspection-only duplicate" not in context


def test_non_collection_result_keeps_existing_bounded_serialization():
    context = OperationExecutionFacade.format_result_for_context(
        ToolResult.ok({"hits": [{"content": "relevant result"}]})
    )

    assert "relevant result" in context
