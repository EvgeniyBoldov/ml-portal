"""
Builtin Tools - встроенные tools для Agent Runtime

All tools use @register_tool decorator which auto-registers them
in the VersionedTool tool_registry upon import.

Collection builtin handler slugs (internal):
- collection.search          — SQL search with DSL filters, sorting, pagination
- collection.doc_search      — internal handler slug for collection.document.search
- collection.template.search — semantic search in template collections (retrieval-enabled text fields)
- collection.list_documents  — list files in a document collection with metadata and storage_uri
- collection.get_document    — get single document metadata and storage_uri
- collection.get             — get single record by primary key
- collection.aggregate       — aggregations (count, sum, avg, min, max, group_by, having)
- collection.info           — collection structure, metadata, and observed filter values for bound collection
- file.generate              — persist generated file (csv/json/txt/md) to chat storage and return storage_uri
- file.read                  — read a file by canonical storage_uri (s3://bucket/key)
- file.analyze               — inspect spreadsheet structure (Excel/CSV) by canonical storage_uri
- file.list                  — list all files in the current chat
- file.delete                — delete a file from chat storage by file_id

Runtime publishes canonical operation names for LLM/planner:
- collection.document.search
- collection.table.search
- collection.template.search
- collection.table.get
- collection.table.aggregate
- collection.info
"""


def register_builtins() -> None:
    """
    Регистрирует все builtin tools.
    
    Импорт модулей активирует @register_tool декоратор,
    который автоматически регистрирует VersionedTool в tool_registry.
    """
    import app.agents.builtins.collection_search  # noqa: F401
    import app.agents.builtins.collection_doc_search  # noqa: F401
    import app.agents.builtins.collection_text_search  # noqa: F401
    import app.agents.builtins.collection_document_list  # noqa: F401
    import app.agents.builtins.collection_document_get  # noqa: F401
    import app.agents.builtins.collection_get  # noqa: F401
    import app.agents.builtins.collection_aggregate  # noqa: F401
    import app.agents.builtins.collection_catalog  # noqa: F401
    import app.agents.builtins.file_generate  # noqa: F401
    import app.agents.builtins.file_read  # noqa: F401
    import app.agents.builtins.file_analyze  # noqa: F401
    import app.agents.builtins.file_list  # noqa: F401
    import app.agents.builtins.file_delete  # noqa: F401
    import app.agents.builtins.template_list  # noqa: F401
    import app.agents.builtins.template_get_schema  # noqa: F401
    import app.agents.builtins.template_fill  # noqa: F401
