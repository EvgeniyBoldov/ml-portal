from app.agents.protocol import build_tools_payload, build_tools_prompt
from app.agents.runtime.prompt_assembler import PromptAssembler


def test_build_tools_prompt_uses_default_mandatory_rules():
    prompt = build_tools_prompt([{"type": "function", "function": {"name": "x", "parameters": {}}}])
    assert "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА" in prompt


def test_build_tools_prompt_uses_override_rules_text():
    prompt = build_tools_prompt(
        [{"type": "function", "function": {"name": "x", "parameters": {}}}],
        mandatory_rules_text="CUSTOM RULES BLOCK",
    )
    assert "CUSTOM RULES BLOCK" in prompt
    assert "MANDATORY RULES" not in prompt


def test_prompt_assembler_resolves_operations_rules_override_priority():
    assembler = PromptAssembler()
    platform = {"operations_rules_text": "platform"}
    sandbox = {"operations_rules_text": "sandbox"}
    assert (
        assembler._resolve_operations_rules_override(
            platform_config=platform,
            sandbox_overrides=sandbox,
        )
        == "sandbox"
    )


def test_build_tools_prompt_includes_collection_selection_guidance():
    prompt = build_tools_prompt([{"type": "function", "function": {"name": "x", "parameters": {}}}])
    assert "выбирай `collection_slug` из допустимых значений в схеме инструмента" in prompt


def test_operation_prompt_renderer_keeps_prompt_minimal_and_collection_aware():
    schema = build_tools_payload([
        type(
            "Op",
            (),
            {
                "operation_slug": "instance.reglament.collection.document.search",
                "operation": "collection.document.search",
                "name": "Document Search",
                "description": "Search documents and return relevant document results",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                "scope": "collection",
                "collection_slug": "reglament",
                "data_instance_slug": "reglament",
                "result_kind": "documents",
                "published": type(
                    "Published",
                    (),
                    {
                        "canonical_name": "collection.document.search",
                        "collection_slug": "reglament",
                        "collection_type": "document",
                        "result_kind": "documents",
                        "title": "Document Search",
                        "description": "Search documents and return relevant document results",
                    },
                )(),
            },
        )()
    ])[0]

    assert schema["function"]["name"] == "collection.document.search"
    assert "Document Search" in schema["function"]["description"]
    assert "requires collection_slug target (document)" in schema["function"]["description"]
    assert "result: documents" in schema["function"]["description"]
    assert "use this first when the task asks for document contents" in schema["function"]["description"]
    assert "exact call name" not in schema["function"]["description"]
    assert "canonical:" not in schema["function"]["description"]
    assert "x-runtime" not in schema
    assert "collection_slug" in schema["function"]["parameters"].get("properties", {})
    assert "collection_slug" in schema["function"]["parameters"].get("required", [])


def test_operation_prompt_renderer_publishes_public_collection_info_schema():
    schema = build_tools_payload([
        type(
            "Op",
            (),
            {
                "operation_slug": "instance.docs.collection.info",
                "operation": "collection.info",
                "name": "Collection Info",
                "description": "Inspect the bound collection schema, metadata, filterable fields, and observed values",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "collection_slug": {"type": "string"},
                    },
                    "required": ["collection_slug"],
                },
                "scope": "collection",
                "collection_slug": "docs",
                "data_instance_slug": "docs",
                "result_kind": "catalog",
                "published": type(
                    "Published",
                    (),
                    {
                        "canonical_name": "collection.info",
                        "collection_slug": "docs",
                        "collection_type": "document",
                        "result_kind": "catalog",
                        "title": "Collection Info",
                        "description": "Inspect the bound collection schema, metadata, filterable fields, and observed values",
                    },
                )(),
            },
        )()
    ])[0]

    assert schema["function"]["name"] == "collection.info"
    assert schema["function"]["parameters"]["properties"]["collection_slug"]["type"] == "string"
    assert schema["function"]["parameters"]["required"] == ["collection_slug"]
    assert "follow coverage.fields.next_offset" in schema["function"]["description"]


def test_operation_prompt_renderer_hides_collection_id_for_bound_template_operation():
    schema = build_tools_payload([
        type(
            "Op",
            (),
            {
                "operation_slug": "instance.templates.collection.template.fill",
                "operation": "collection.template.fill",
                "name": "Fill Template",
                "description": "Fill a template with values and return a generated file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "collection_id": {"type": "string"},
                        "row_id": {"type": "string"},
                        "values": {"type": "object"},
                    },
                    "required": ["collection_id", "row_id", "values"],
                },
                "scope": "collection",
                "collection_slug": "template",
                "data_instance_slug": "template",
                "result_kind": "file",
                "published": type(
                    "Published",
                    (),
                    {
                        "canonical_name": "collection.template.fill",
                        "collection_slug": "template",
                        "collection_type": "template",
                        "result_kind": "file",
                        "title": "Fill Template",
                        "description": "Fill a template with values and return a generated file",
                    },
                )(),
            },
        )()
    ])[0]

    assert "collection_id" not in schema["function"]["parameters"].get("properties", {})
    assert "collection_id" not in schema["function"]["parameters"].get("required", [])
    assert "row_id from collection.template.search or collection.template.list" in schema["function"]["description"]


def test_prompt_assembler_operation_schemas_include_collection_tools_from_first_call():
    assembler = PromptAssembler()
    operations = [
        type(
            "Op",
            (),
            {
                "scope": "collection",
                "operation": "collection.info",
                "operation_slug": "instance.template.collection.info",
                "name": "Collection Info",
                "description": "Inspect collection",
                "input_schema": {},
                "collection_slug": "template",
                "data_instance_slug": "template",
                "result_kind": "catalog",
                "published": type("Published", (), {"canonical_name": "collection.info"})(),
            },
        )(),
        type(
            "Op",
            (),
            {
                "scope": "collection",
                "operation": "collection.template.search",
                "operation_slug": "instance.template.collection.template.search",
                "name": "Search Templates",
                "description": "Search templates",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                "collection_slug": "template",
                "data_instance_slug": "template",
                "result_kind": "rows",
                "published": type("Published", (), {"canonical_name": "collection.template.search"})(),
            },
        )(),
        type(
            "Op",
            (),
            {
                "scope": "system",
                "operation": "file.read",
                "operation_slug": "file.read",
                "name": "Read File",
                "description": "Read file",
                "input_schema": {},
                "result_kind": "file",
                "published": type("Published", (), {"canonical_name": "file.read"})(),
            },
        )(),
    ]
    schemas = assembler.assemble_operation_schemas(operations)

    names = [item["function"]["name"] for item in schemas]
    assert "collection.info" in names
    assert "file.read" in names
    assert "collection.template.search" in names
    assert "collection_slug" in schemas[1]["function"]["parameters"]["required"]
    native_names = [item["function"]["name"] for item in build_tools_payload(operations)]
    assert native_names == ["collection.info", "collection.template.search", "file.read"]


def test_prompt_assembler_omits_text_tool_contract_for_native_tool_calling():
    assembler = PromptAssembler()
    assembly = assembler.assemble(
        type("Request", (), {"policy_data": {}, "limit_data": {}, "resolved_data_instances": []})(),
        system_prompt_override="base prompt",
        resolved_operations=[],
        operation_schemas=[
            {"type": "function", "function": {"name": "file.read", "parameters": {}}}
        ],
        platform_config={"native_tool_calling": True},
    )

    assert assembly.operations_prompt == ""
    assert "Список инструментов:" not in assembly.system_prompt


def test_operation_descriptions_are_complete_in_native_and_text_schemas():
    from types import SimpleNamespace

    description = "Operation details. " * 100 + "FINAL_CONSTRAINT"
    operation = SimpleNamespace(
        operation="test_operation", operation_slug="test_operation", name="Test",
        scope="system", description=description, published=None,
        input_schema={"type": "object", "properties": {}}, result_kind="rows",
    )
    native = build_tools_payload([operation])[0]["function"]["description"]
    rendered = PromptAssembler().assemble_operation_schemas([operation])[0]["function"]["description"]
    assert description in native
    assert description in rendered
    assert native == rendered
