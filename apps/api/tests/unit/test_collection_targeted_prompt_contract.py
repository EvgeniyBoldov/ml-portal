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
