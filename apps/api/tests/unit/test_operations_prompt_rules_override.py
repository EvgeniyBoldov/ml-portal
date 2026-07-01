from app.agents.protocol import build_operations_prompt
from app.agents.runtime.prompt_assembler import OperationPromptRenderer, PromptAssembler, filter_prompt_visible_operations


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
    assert "сначала вызови `collection.info`" in prompt.lower()
    assert "которые вернулись в результате `collection.info`" in prompt
    assert "имя инструмента ровно в том виде" in prompt


def test_prompt_assembler_separates_collection_and_system_sections():
    assembler = PromptAssembler()
    collection_prompt = assembler.assemble_collection_prompt(
        [
            type(
                "Collection",
                (),
                {
                    "collection_slug": "reglament",
                    "slug": "reglament",
                    "collection_type": "document",
                    "domain": "collection.document",
                    "usage_purpose": "Искать регламенты",
                    "data_description": "Документы с регламентами",
                    "usage_rules": "Сначала info, потом search.",
                    "remote_tables": [],
                },
            )()
        ],
        resolved_operations=[
            type(
                "Op",
                (),
                {
                    "scope": "collection",
                    "collection_slug": "reglament",
                    "operation": "collection.document.search",
                    "operation_slug": "instance.reglament.collection.document.search",
                    "name": "Document Search",
                    "published": type(
                        "Published",
                        (),
                        {
                            "title": "Document Search",
                            "description": "Search documents and return relevant results",
                            "result_kind": "documents",
                        },
                    )(),
                },
            )()
        ],
    )
    system_prompt = assembler.assemble_system_operations_prompt(
        resolved_operations=[
            type(
                "Op",
                (),
                {
                    "scope": "system",
                    "operation": "file.generate",
                    "operation_slug": "file.generate",
                    "name": "Generate File",
                    "published": type(
                        "Published",
                        (),
                        {
                            "canonical_name": "file.generate",
                            "title": "Generate File",
                            "description": "Save generated content to chat storage",
                            "result_kind": "generic",
                        },
                    )(),
                },
            )()
        ]
    )

    assert "## Доступные коллекции" in collection_prompt
    assert "сначала вызови `collection.info`" in collection_prompt.lower()
    assert "collection.document.search" not in collection_prompt
    assert "рекомендуемый порядок" not in collection_prompt
    assert "## Системные операции" in system_prompt
    assert "`file.generate`" in system_prompt


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
    assert "use this first when the task asks for document contents" in schema["function"]["description"]
    assert "exact call name" not in schema["function"]["description"]
    assert "canonical:" not in schema["function"]["description"]
    assert "x-runtime" not in schema
    assert "collection_slug" not in schema["function"]["parameters"].get("properties", {})
    assert "collection_slug" not in schema["function"]["parameters"].get("required", [])


def test_operation_prompt_renderer_publishes_public_collection_info_schema():
    schema = OperationPromptRenderer.render_public_collection_info_schema(
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
    )

    assert schema["function"]["name"] == "collection.info"
    assert schema["function"]["parameters"]["properties"]["collection_slug"]["type"] == "string"
    assert schema["function"]["parameters"]["required"] == ["collection_slug"]
    assert "inspect one available collection by slug" in schema["function"]["description"]


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
    assert "row_id must come from collection.template.list" in schema["function"]["description"]


def test_prompt_assembler_operation_schemas_keep_only_collection_info_and_system():
    assembler = PromptAssembler()
    operations = [
        type(
            "Op",
            (),
            {
                "scope": "collection",
                "operation": "collection.info",
                "operation_slug": "instance.template.collection.info",
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
                "published": type("Published", (), {"canonical_name": "file.read"})(),
            },
        )(),
    ]
    schemas = assembler.assemble_operation_schemas(operations)

    names = [item["function"]["name"] for item in schemas]
    assert "collection.info" in names
    assert "file.read" in names
    assert "instance.template.collection.template.search" not in names

    visible_names = [item.operation_slug for item in filter_prompt_visible_operations(operations)]
    assert visible_names == ["instance.template.collection.info", "file.read"]
