"""
Tool Registry - реестр всех доступных tool handlers
"""
from __future__ import annotations
from typing import Dict, List, Optional, Type
import logging

from app.agents.handlers.base import ToolHandler

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Singleton реестр tool handlers.
    
    Все builtin tools регистрируются при импорте модуля builtins.
    Custom tools могут регистрироваться динамически.
    
    Использование:
        # Регистрация
        ToolRegistry.register(MyToolHandler())
        
        # Получение
        handler = ToolRegistry.get("my.tool")
        
        # Получение tools для агента
        handlers = ToolRegistry.get_for_agent(["rag.search", "jira.create"])
    """
    
    _handlers: Dict[str, ToolHandler] = {}
    _initialized: bool = False
    
    @classmethod
    def register(cls, handler: ToolHandler) -> None:
        """
        Зарегистрировать tool handler.
        
        Args:
            handler: Экземпляр ToolHandler
        """
        slug = handler.slug
        if slug in cls._handlers:
            logger.warning(f"Tool '{slug}' already registered, overwriting")
        
        cls._handlers[slug] = handler
        logger.info(f"Registered tool: {slug}")
    
    @classmethod
    def register_class(cls, handler_class: Type[ToolHandler]) -> None:
        """
        Зарегистрировать tool handler по классу (создаёт экземпляр).
        """
        cls.register(handler_class())
    
    @classmethod
    def get(cls, slug: str) -> Optional[ToolHandler]:
        """
        Получить handler по slug.
        """
        cls._ensure_initialized()
        return cls._handlers.get(slug)
    
    @classmethod
    def get_for_agent(cls, tool_slugs: List[str]) -> List[ToolHandler]:
        """
        Получить список handlers для агента.
        Пропускает неизвестные slugs с warning.
        """
        cls._ensure_initialized()
        handlers = []
        for slug in tool_slugs:
            handler = cls._handlers.get(slug)
            if handler:
                handlers.append(handler)
            else:
                logger.warning(f"Tool '{slug}' not found in registry")
        return handlers
    
    @classmethod
    def list_all(cls) -> List[ToolHandler]:
        """
        Получить все зарегистрированные handlers.
        """
        cls._ensure_initialized()
        return list(cls._handlers.values())
    
    @classmethod
    def list_slugs(cls) -> List[str]:
        """
        Получить все зарегистрированные slugs.
        """
        cls._ensure_initialized()
        return list(cls._handlers.keys())
    
    @classmethod
    def _ensure_initialized(cls) -> None:
        """
        Ленивая инициализация builtin tools.
        """
        if cls._initialized:
            return
        
        try:
            from app.agents.builtins import register_builtins
            register_builtins()
            cls._initialized = True
        except ImportError as e:
            logger.error(f"Failed to import builtins: {e}")
            cls._initialized = True
    
    @classmethod
    def clear(cls) -> None:
        """
        Очистить реестр (для тестов).
        """
        cls._handlers.clear()
        cls._initialized = False
