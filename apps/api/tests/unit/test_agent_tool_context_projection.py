import json

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


def test_context_projection_includes_runtime_evidence_call_id_only_when_provided():
    context = OperationExecutionFacade.format_result_for_context(
        ToolResult.ok({"hits": [{"artifact_id": "document-1"}]}),
        operation_slug="collection.document.search",
        evidence_call_id="runtime-search-1",
    )

    assert '"evidence_call_id": "runtime-search-1"' in context
    assert '"artifact_id": "document-1"' in context


def test_collection_info_native_projection_omits_duplicate_tool_contracts():
    context = OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(
            {
                "collection": {
                    "slug": "template_test",
                    "description": "Template registry",
                    "usage_rules": "Search, get schema, then fill.",
                },
                "readiness": {"status": "ready"},
                "tools": [{"tool_name": "collection.template.search"}],
            }
        ),
        operation_slug="instance.local-template-tools.collection.info",
        include_operation_contracts=False,
    )

    assert "collection.template.search" not in context
    assert "Search, get schema, then fill." in context


def test_template_context_projections_keep_only_next_call_contract():
    search = OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(
            {
                "collection": "template_test",
                "hits": [
                    {
                        "row_id": "row-1",
                        "score": 0.9,
                        "primary_fragment": "Network connectivity request",
                        "row_data": {
                            "title": "Connectivity request",
                            "template_schema": {"must_not": "be repeated"},
                            "source": "must_not_enter_context",
                        },
                    }
                ],
            }
        ),
        operation_slug="instance.local-template-tools.collection.template.search",
    )
    assert json.loads(search) == {
        "collection": "template_test",
        "hits": [{"row_id": "row-1", "title": "Connectivity request", "score": 0.9, "match": "Network connectivity request"}],
        "total": 1,
    }

    schema = OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(
            {
                "row_id": "row-1",
                "title": "Connectivity request",
                "source": "must_not_enter_context",
                "template_schema": {"type": "object", "properties": {"table": {"type": "object"}}},
                "runtime_schema": {"must_not": "be repeated"},
            }
        ),
        operation_slug="instance.local-template-tools.collection.template.get_schema",
    )
    assert json.loads(schema) == {
        "template_schema": {"type": "object", "properties": {"table": {"type": "object"}}}
    }

    filled = OperationExecutionFacade.format_result_for_context(
        ToolResult.ok(
            {
                "artifact_id": "artifact-1",
                "file_name": "request.xlsx",
                "content_type": "application/vnd.ms-excel",
                "size_bytes": 42,
                "filled_placeholders": 10,
            }
        ),
        operation_slug="instance.local-template-tools.collection.template.fill",
    )
    assert json.loads(filled) == {
        "artifact_id": "artifact-1",
        "file_name": "request.xlsx",
        "content_type": "application/vnd.ms-excel",
        "size_bytes": 42,
    }
