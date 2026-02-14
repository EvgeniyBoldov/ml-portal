"""
Builtin Tools - встроенные tools для Agent Runtime

All tools use @register_tool decorator which auto-registers them
in the VersionedTool tool_registry upon import.
"""


def register_builtins() -> None:
    """
    Регистрирует все builtin tools.
    
    Импорт модулей активирует @register_tool декоратор,
    который автоматически регистрирует VersionedTool в tool_registry.
    """
    import app.agents.builtins.rag_search  # noqa: F401
    import app.agents.builtins.collection_search  # noqa: F401
    import app.agents.builtins.collection_get  # noqa: F401
    import app.agents.builtins.collection_aggregate  # noqa: F401
    import app.agents.builtins.tool_router  # noqa: F401
    # DCBox (NetBox) remote tools
    import app.agents.builtins.dcbox_devices  # noqa: F401
    import app.agents.builtins.dcbox_sites  # noqa: F401
    import app.agents.builtins.dcbox_racks  # noqa: F401
    import app.agents.builtins.dcbox_prefixes  # noqa: F401
    import app.agents.builtins.dcbox_addresses  # noqa: F401
