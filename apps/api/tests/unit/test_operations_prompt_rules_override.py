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
    assert "collection: reglament (document)" in schema["function"]["description"]
    assert "result: documents" in schema["function"]["description"]
    assert "exact call name" not in schema["function"]["description"]
    assert "canonical:" not in schema["function"]["description"]
    assert "x-runtime" not in schema
