"""
Builtin Tools - встроенные tools для Agent Runtime
"""
from app.agents.registry import ToolRegistry


def register_builtins() -> None:
    """
    Регистрирует все builtin tools.
    Вызывается лениво при первом обращении к ToolRegistry.
    """
    from app.agents.builtins.rag_search import RagSearchTool
    from app.agents.builtins.collection_search import CollectionSearchTool
    
    ToolRegistry.register(RagSearchTool())
    ToolRegistry.register(CollectionSearchTool())
