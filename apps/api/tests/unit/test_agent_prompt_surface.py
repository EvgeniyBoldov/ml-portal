from types import SimpleNamespace

import pytest

from app.agents.protocol import build_tools_payload
from app.agents.runtime.prompt_assembler import PromptAssembler
from app.runtime.orchestrator_contracts import TaskRequest
from app.runtime.task_completion_prompt import build_task_completion_prompt
from app.services.collection_tool_resolver import CollectionToolResolutionContext, CollectionToolResolver


def test_native_prompt_keeps_usage_but_does_not_repeat_tool_contracts():
    collection = SimpleNamespace(collection_slug="inventory", slug="inventory", name="Inventory",
        collection_type="api", usage_purpose="Read devices", data_description="Device inventory",
        usage_rules="List objects; search only by non-empty text.", remote_tables=[],
        schema_fields=[{"name": "examples", "type": "json"}])
    operation = SimpleNamespace(scope="collection", collection_slug="inventory",
        operation="get_devices", operation_slug="collection.inventory.get_devices", name="Devices",
        description="UNIQUE_TOOL_DESCRIPTION", published=None,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}})
    system = SimpleNamespace(scope="system", operation="file.read", operation_slug="file.read",
        name="Read", description="UNIQUE_SYSTEM_DESCRIPTION", published=None, input_schema={})
    request = SimpleNamespace(policy_data={}, limit_data={}, resolved_data_instances=[collection])
    prompt = PromptAssembler().assemble(request, system_prompt_override="base",
        resolved_operations=[operation, system], platform_config={"native_tool_calling": True}).system_prompt
    assert collection.usage_rules in prompt
    assert "`get_devices`" in prompt
    assert "UNIQUE_TOOL_DESCRIPTION" not in prompt
    assert "UNIQUE_SYSTEM_DESCRIPTION" not in prompt
    assert "вход:" not in prompt
    assert "метаданные каталога" in prompt
    assert "result.describe" in prompt


def test_platform_policy_is_preserved_even_with_legacy_character_budget():
    policy = "Полное правило. " * 150 + "END_OF_POLICY"
    request = SimpleNamespace(policy_data={}, limit_data={}, resolved_data_instances=[])
    prompt = PromptAssembler().assemble(request, system_prompt_override="base",
        platform_config={"policies_text": policy, "prompt_budgets": {"policies_text_max_chars": 20}}).system_prompt
    assert policy in prompt


def test_completion_prompt_has_one_presentation_schema_and_no_legacy_execution_fields():
    schema = {"type": "object", "properties": {"unique_device_field": {"type": "string"}}}
    task = TaskRequest(task_id="task", executor="agent", intent="read", instructions="read",
        response_spec={"mode": "structured", "schema": schema},
        expected_outputs=[{"key": "devices", "description": "devices", "schema": schema}])
    prompt = build_task_completion_prompt(task)
    assert prompt.count("unique_device_field") == 1
    assert "Legacy presentation" not in prompt
    assert "receipt_operations" not in prompt
    assert "legacy journal adapter" not in prompt
    assert "result.read" in prompt


@pytest.mark.parametrize("collection_type", ["document", "template", "table", "api"])
def test_local_provider_exposes_only_tools_matching_bound_collection_type(collection_type):
    context = CollectionToolResolutionContext(instance=SimpleNamespace(), provider=SimpleNamespace(),
        bound_collection=SimpleNamespace(collection_type=collection_type),
        runtime_domain=f"collection.{collection_type}", provider_kind="local")
    for tool_type in ["document", "template", "table"]:
        tool = SimpleNamespace(source="local", slug=f"custom_{tool_type}", domains=[f"collection.{tool_type}"])
        assert CollectionToolResolver._is_tool_supported_for_context(tool=tool, context=context) is (tool_type == collection_type)


def test_native_collection_target_enum_contains_only_executable_bindings():
    def operation(slug):
        return SimpleNamespace(scope="collection", collection_slug=slug, operation="get_devices",
            operation_slug=f"collection.{slug}.get_devices", description="Read", name="Read",
            input_schema={}, published=None)
    tools = build_tools_payload([operation("netbox"), operation("inventory")])
    assert len(tools) == 1
    assert tools[0]["function"]["parameters"]["properties"]["collection_slug"]["enum"] == ["inventory", "netbox"]


def test_native_tools_omit_unbound_operations_and_internal_runtime_metadata():
    unbound = SimpleNamespace(scope="collection", collection_slug=None, operation="get_devices",
        operation_slug="get_devices", description="Read", name="Read", input_schema={}, published=None)
    system = SimpleNamespace(scope="system", operation="test.read", operation_slug="test.read",
        name="Read", description="Read", published=None,
        input_schema={"type": "object", "properties": {"x-runtime": {"type": "string"}},
            "x-runtime": {"credential_scope": "platform"}})
    tools = build_tools_payload([unbound, system])
    assert [item["function"]["name"] for item in tools] == ["test.read"]
    schema = tools[0]["function"]["parameters"]
    assert "x-runtime" not in schema
    assert "x-runtime" in schema["properties"]


def test_completion_protocol_schema_keeps_description_as_a_data_field():
    import json
    import jsonschema
    from app.runtime.orchestrator_contracts import task_completion_json_schema

    task = TaskRequest(task_id="task", executor="agent", intent="read", instructions="read")
    prompt = build_task_completion_prompt(task)
    schema = json.loads(prompt.split("JSON Schema протокола из Pydantic:\n", 1)[1])
    jsonschema.Draft202012Validator.check_schema(schema)
    payload = {"completion": "needs", "needs": [{"ref": "site", "key": "site", "description": "Choose site"}]}
    jsonschema.validate(payload, schema)
    jsonschema.validate(payload, task_completion_json_schema(task))
    assert "description" in schema["$defs"]["DiscoveredNeed"]["properties"]
