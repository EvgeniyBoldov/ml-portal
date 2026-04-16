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

Runtime publishes canonical operation names for LLM/planner:
- collection.document.search
- collection.table.search
- collection.table.get
- collection.table.aggregate
- collection.table.catalog_inspect
- collection.document.catalog_inspect
- collection.sql.catalog_inspect
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
