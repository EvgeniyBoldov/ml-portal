"""
Builtin Tools - встроенные tools для Agent Runtime

All tools use @register_tool decorator which auto-registers them
in the VersionedTool tool_registry upon import.

Collection builtin handler slugs (internal):
- collection.search      — SQL search with DSL filters, sorting, pagination
- collection.doc_search  — semantic search in document collections
- collection.text_search — semantic search in table collections (retrieval-enabled text fields)
- collection.get         — get single record by primary key
- collection.aggregate   — aggregations (count, sum, avg, min, max, group_by, having)
- collection.catalog     — schema/data-shape inspection for any collection type
- file.generate          — persist generated file (csv/json/txt/md) to chat storage
- file.read              — read a previously uploaded or generated file from chat storage
- file.list              — list all files in the current chat
- file.delete            — delete a file from chat storage by file_id

Runtime publishes canonical operation names for LLM/planner:
- collection.document.search
- collection.table.search
- collection.table.get
- collection.table.aggregate
- collection.catalog_inspect
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
    import app.agents.builtins.collection_get  # noqa: F401
    import app.agents.builtins.collection_aggregate  # noqa: F401
    import app.agents.builtins.collection_catalog  # noqa: F401
    import app.agents.builtins.file_generate  # noqa: F401
    import app.agents.builtins.file_read  # noqa: F401
    import app.agents.builtins.file_list  # noqa: F401
    import app.agents.builtins.file_delete  # noqa: F401
