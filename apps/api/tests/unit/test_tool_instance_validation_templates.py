from app.services.tool_instance.validation import ToolInstanceValidationService


def test_infer_service_provider_kind_recognizes_local_template_service():
    assert (
        ToolInstanceValidationService.infer_service_provider_kind(
            placement="local",
            domain="collection.template",
            slug="local-template-tools",
            local_table_service_slug="local-table-tools",
            local_document_service_slug="local-document-tools",
            local_template_service_slug="local-template-tools",
            local_runtime_service_slug="local-runtime",
        )
        == "local_templates"
    )
