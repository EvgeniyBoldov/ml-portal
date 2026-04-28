"""
Tool Registry - реестр всех доступных tool handlers
"""
from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional, Type
from app.core.logging import get_logger

from app.agents.handlers.base import ToolHandler

logger = get_logger(__name__)


class _VersionedToolWrapper(ToolHandler):
    """
    Обёртка VersionedTool → ToolHandler для обратной совместимости с runtime.
    Делегирует execute/validate_args в VersionedTool с фиксированной версией.
    """
    
    def __init__(self, versioned_tool, version: str):
        self._vt = versioned_tool
        self._version = version
        vi = versioned_tool.get_version(version)
        self.slug = versioned_tool.tool_slug
        self.name = versioned_tool.name
        self.description = versioned_tool.description
        self.domains = getattr(versioned_tool, 'domains', [])
        self.input_schema = vi.input_schema if vi else {}
        self.output_schema = vi.output_schema if vi else None
    
    async def execute(self, ctx, args):
        return await self._vt.execute(ctx, args, version=self._version)
    
    def validate_args(self, args):
        return self._vt.validate_args(args, version=self._version)


class ToolRegistry:
    """
    Реестр tool handlers.

    Поддерживает два режима:
    - Class-level singleton (обратная совместимость): `ToolRegistry.get(slug)`.
    - Instance API (DI / тесты): `registry = ToolRegistry(); registry.get(slug)`.

    Для инжекции через assembler используйте `ToolRegistry.get_instance()`.
    Для изолированных тестов создавайте `ToolRegistry()` напрямую.
    """

    _handlers: Dict[str, ToolHandler] = {}
    _initialized: bool = False
    _init_lock: threading.Lock = threading.Lock()

    _global_instance: "Optional[ToolRegistry]" = None

    def __init__(self, *, _use_class_store: bool = False) -> None:
        if _use_class_store:
            self._instance_handlers = None  # uses class-level dict
        else:
            self._instance_handlers: Optional[Dict[str, ToolHandler]] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Return the shared singleton instance (DI-friendly). Creates it on first call."""
        if cls._global_instance is None:
            cls._global_instance = cls(_use_class_store=True)
        return cls._global_instance

    # ------------------------------------------------------------------
    # Instance-level API (DI / test isolation)
    # ------------------------------------------------------------------

    def _store(self) -> Dict[str, ToolHandler]:
        """Return the handler store for this instance."""
        if self._instance_handlers is not None:
            return self._instance_handlers
        self.__class__._ensure_initialized()
        return self.__class__._handlers

    def register_handler(self, handler: ToolHandler) -> None:
        """Register a handler on this instance (does not affect the class-level singleton)."""
        slug = handler.slug
        store = self._store()
        if slug in store:
            logger.warning(f"Tool '{slug}' already registered on instance, overwriting")
        store[slug] = handler

    def get_handler(self, slug: str) -> Optional[ToolHandler]:
        """Get a handler by slug from this instance's store."""
        return self._store().get(slug)

    def list_handlers(self) -> List[ToolHandler]:
        """List all handlers registered on this instance."""
        return list(self._store().values())

    def clear_handlers(self) -> None:
        """Clear all handlers on this instance (safe for test teardown)."""
        store = self._store()
        store.clear()
        if self._instance_handlers is None:
            self.__class__._initialized = False

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
    def list_mcp_descriptors(
        cls,
        slugs: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получить MCP-compatible descriptors для локальных handlers.
        """
        handlers = cls.get_for_agent(slugs) if slugs is not None else cls.list_all()
        return [handler.to_mcp_descriptor() for handler in handlers]
    
    @classmethod
    def list_by_domain(cls, domain: str) -> List[ToolHandler]:
        """
        Получить handlers, которые обслуживают указанный domain.
        """
        cls._ensure_initialized()
        return [
            h for h in cls._handlers.values()
            if domain in (getattr(h, 'domains', None) or [])
        ]

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
        
        1. Импортирует builtins (активирует @register_tool → tool_registry)
        2. Создаёт ToolHandler-совместимые обёртки из VersionedTool
           для обратной совместимости с runtime
        """
        if cls._initialized:
            return
        with cls._init_lock:
            if cls._initialized:
                return
            try:
                from app.agents.builtins import register_builtins
                register_builtins()
                
                # Bridge: wrap VersionedTool instances as ToolHandler-compatible
                cls._bridge_versioned_tools()
                
                cls._initialized = True
            except ImportError as e:
                logger.error(f"Failed to import builtins: {e}")
                cls._initialized = True
    
    @classmethod
    def _bridge_versioned_tools(cls) -> None:
        """
        Создаёт ToolHandler-совместимые обёртки для всех VersionedTool
        из tool_registry, чтобы runtime мог использовать ToolRegistry.get().
        """
        try:
            from app.agents.handlers.versioned_tool import tool_registry
            
            for vt in tool_registry.get_all():
                if vt.tool_slug in cls._handlers:
                    continue  # Already registered as ToolHandler
                
                all_versions = vt.get_versions()
                latest = next(
                    (v for v in all_versions if not v.deprecated),
                    all_versions[0] if all_versions else None,
                )
                if not latest:
                    continue
                if latest.deprecated:
                    logger.warning(
                        f"All versions of VersionedTool '{vt.tool_slug}' are deprecated; skipping bridge"
                    )
                    continue
                
                # Create a lightweight ToolHandler wrapper
                wrapper = _VersionedToolWrapper(vt, latest.version)
                cls._handlers[vt.tool_slug] = wrapper
                logger.info(f"Bridged VersionedTool as ToolHandler: {vt.tool_slug}@{latest.version}")
        except ImportError:
            pass
    
    @classmethod
    def clear(cls) -> None:
        """
        Очистить реестр (для тестов).
        """
        cls._handlers.clear()
        cls._initialized = False
