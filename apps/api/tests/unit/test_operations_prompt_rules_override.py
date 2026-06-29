from app.agents.protocol import build_operations_prompt
from app.agents.runtime.prompt_assembler import OperationPromptRenderer, PromptAssembler


def test_build_operations_prompt_uses_default_mandatory_rules():
    prompt = build_operations_prompt([{"type": "function", "function": {"name": "x", "parameters": {}}}])
    assert "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА" in prompt


def test_build_operations_prompt_uses_override_rules_text():
    prompt = build_operations_prompt(
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


def test_build_operations_prompt_includes_collection_selection_guidance():
    prompt = build_operations_prompt([{"type": "function", "function": {"name": "x", "parameters": {}}}])
    assert "Сначала сопоставь задачу с нужной коллекцией" in prompt
    assert "точное имя из `function.name`" in prompt


def test_operation_prompt_renderer_keeps_prompt_minimal_and_collection_aware():
    schema = OperationPromptRenderer.render_schema(
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
    )

    assert schema["function"]["name"] == "instance.reglament.collection.document.search"
    assert "Document Search" in schema["function"]["description"]
    assert "bound to collection: reglament (document)" in schema["function"]["description"]
    assert "result: documents" in schema["function"]["description"]
    assert "exact call name" not in schema["function"]["description"]
    assert "canonical:" not in schema["function"]["description"]
    assert "x-runtime" not in schema
    assert "collection_slug" not in schema["function"]["parameters"].get("properties", {})
    assert "collection_slug" not in schema["function"]["parameters"].get("required", [])


def test_operation_prompt_renderer_hides_collection_slug_for_bound_collection_info():
    schema = OperationPromptRenderer.render_schema(
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
                        "dimensions": {"type": "array"},
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
    )

    assert "collection_slug" not in schema["function"]["parameters"].get("properties", {})
    assert "collection_slug" not in schema["function"]["parameters"].get("required", [])


def test_operation_prompt_renderer_hides_collection_id_for_bound_template_operation():
    schema = OperationPromptRenderer.render_schema(
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
    )

    assert "collection_id" not in schema["function"]["parameters"].get("properties", {})
    assert "collection_id" not in schema["function"]["parameters"].get("required", [])
