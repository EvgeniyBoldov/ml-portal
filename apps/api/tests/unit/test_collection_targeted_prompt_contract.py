import json

import pytest

from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.protocol import build_tools_payload
from app.agents.runtime.prompt_contract import build_prompt_input_schema
from app.agents.runtime.published_capabilities import serialize_published_operations


def _operation() -> ResolvedOperation:
    return ResolvedOperation(
        operation_slug="collection.atlant.collection.template.search",
        operation="collection.template.search",
        name="Search Templates",
        scope="collection",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        data_instance_id="local-template-tools",
        data_instance_slug="local-template-tools",
        collection_slug="atlant",
        source="local",
        target=ProviderExecutionTarget(
            operation_slug="collection.atlant.collection.template.search",
            provider_type="local",
            data_instance_id="local-template-tools",
            data_instance_slug="local-template-tools",
            handler_slug="collection.template.search",
        ),
    )


def test_collection_tool_schema_requires_explicit_collection_slug() -> None:
    schema = build_prompt_input_schema(_operation())

    assert schema["required"] == ["collection_slug", "query"]
    assert "collection_slug" in schema["properties"]
    assert "collection_id" not in schema["properties"]


def test_prompt_publishes_one_canonical_tool_for_multiple_collection_bindings() -> None:
    atlant = _operation()
    generic = _operation()
    generic.operation_slug = "collection.generic.collection.template.search"
    generic.target.operation_slug = generic.operation_slug
    generic.collection_slug = "generic"

    tools = build_tools_payload([atlant, generic])

    assert [item["function"]["name"] for item in tools] == ["collection.template.search"]
    assert "collection_slug" in tools[0]["function"]["parameters"]["required"]


def test_published_operation_snapshot_groups_collection_bindings() -> None:
    atlant = _operation()
    generic = _operation()
    generic.operation_slug = "collection.generic.collection.template.search"
    generic.target.operation_slug = generic.operation_slug
    generic.collection_slug = "generic"

    published = serialize_published_operations([atlant, generic])

    assert len(published) == 1
    assert published[0]["canonical_name"] == "collection.template.search"
    assert published[0]["collection_slug"] is None
    assert published[0]["collection_slugs"] == ["atlant", "generic"]


def test_jira_subtasks_are_requested_as_fields_not_include_sections():
    from app.agents.runtime.tools import OperationExecutionFacade
    from app.agents.runtime.prompt_contract import build_prompt_operation_description
    operation = _operation().model_copy(update={"operation": "jira_get_issue"})
    error = OperationExecutionFacade._validate_args(operation, {"include": "subtasks"})
    assert error is not None
    assert error.field_path == "$.include"
    assert "parent = ISSUE_KEY" in error.message
    description = build_prompt_operation_description(operation)
    assert "not an include value" in description
    assert "missing or null subtasks" in description


def test_both_calling_modes_keep_targets_and_nested_schema_references() -> None:
    from jsonschema import Draft202012Validator
    from app.agents.runtime.prompt_assembler import PromptAssembler

    operation = _operation()
    operation.input_schema = {
        "type": "object",
        "properties": {"filter": {"$ref": "#/$defs/Filter"}},
        "$defs": {"Filter": {"type": "object", "required": ["name"]}},
    }
    operations = [operation.model_copy(update={"collection_slug": f"target-{index}"}) for index in range(25)]
    declarations = build_tools_payload(operations)
    assert PromptAssembler().assemble_operation_schemas(operations) == declarations
    parameters = declarations[0]["function"]["parameters"]
    assert "target-24" in parameters["properties"]["collection_slug"]["enum"]
    validator = Draft202012Validator(parameters)
    assert validator.is_valid({"collection_slug": "target-24", "filter": {"name": "example"}})
    assert not validator.is_valid({"collection_slug": "target-24", "filter": {}})


@pytest.mark.parametrize("resource_id", [None, "https://example.invalid/shared-schema"])
def test_different_collection_schemas_validate_calls_in_both_modes(resource_id: str | None) -> None:
    from jsonschema import Draft202012Validator

    from app.agents.protocol import parse_llm_response, parse_native_tool_calls
    from app.agents.runtime.prompt_assembler import PromptAssembler

    def schema(key, value_type):
        result = {
            "type": "object",
            "additionalProperties": False,
            "properties": {key: {"$ref": f"{resource_id or ''}#/$defs/Value"}},
            "required": [key],
            "$defs": {"Value": {"type": value_type}},
        }
        if resource_id:
            result["$id"] = resource_id
        return result

    first = _operation().model_copy(update={"input_schema": schema("query", "string")})
    second = first.model_copy(update={
        "collection_slug": "inventory",
        "input_schema": schema("port", "integer"),
    })
    third = second.model_copy(update={"collection_slug": "inventory-copy"})
    operations = [first, second, third]
    declarations = build_tools_payload(operations)
    assert PromptAssembler().assemble_operation_schemas(operations) == declarations
    function = declarations[0]["function"]
    parameters = function["parameters"]
    assert parameters["required"] == ["collection_slug"]
    assert parameters["properties"]["collection_slug"]["enum"] == ["atlant", "inventory", "inventory-copy"]
    assert len(parameters["anyOf"]) == 2
    Draft202012Validator.check_schema(parameters)
    validator = Draft202012Validator(parameters)

    for args, valid in [
        ({"collection_slug": "atlant", "query": "router"}, True),
        ({"collection_slug": "inventory", "port": 1}, True),
        ({"collection_slug": "inventory-copy", "port": 0}, True),
        ({"collection_slug": "inventory", "port": "1"}, False),
        ({"collection_slug": "inventory", "query": "router"}, False),
        ({"collection_slug": "atlant", "query": "router", "port": 1}, False),
        ({"collection_slug": "atlant"}, False),
        ({"port": 1}, False),
        ({"collection_slug": "other", "port": 1}, False),
    ]:
        text_call = json.dumps({"tool": function["name"], "arguments": args})
        text_parsed = parse_llm_response(text_call)
        native_parsed = parse_native_tool_calls({
            "choices": [{"message": {"tool_calls": [{"id": "call-1", "function": {
                "name": function["name"], "arguments": json.dumps(args),
            }}]}}],
        })
        assert native_parsed is not None
        assert validator.is_valid(text_parsed.tool_calls[0].arguments) == valid
        assert validator.is_valid(native_parsed.tool_calls[0].arguments) == valid
