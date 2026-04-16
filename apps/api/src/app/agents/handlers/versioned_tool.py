"""
Versioned Tool Base Class

Абстрактный класс для инструментов с поддержкой версионирования.
Каждый инструмент должен наследовать этот класс и определять версии как методы.

Структура версионирования:
- Класс инструмента определяет tool_slug и domains
- Каждая версия — это метод класса с декоратором @tool_version
- При старте воркера все версии регистрируются в БД как ToolBackendRelease

Пример:
    class JiraSearchTool(VersionedTool):
        tool_slug = "jira.search"
        domains = ["jira"]
        name = "Jira Search"
        description = "Search Jira issues"
        
        @tool_version("1.0.0")
        async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
            '''First version with basic search'''
            # implementation
            pass
        
        @tool_version("1.1.0")  
        async def v1_1_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
            '''Added JQL support'''
            # implementation
            pass
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, ClassVar, List, Callable
from dataclasses import dataclass
from functools import wraps
import inspect

from app.agents.context import ToolContext, ToolResult


@dataclass
class ToolVersionInfo:
    """Информация о версии инструмента"""
    version: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]]
    description: str
    method_name: str
    deprecated: bool = False
    deprecation_message: Optional[str] = None


@dataclass  
class ToolVersionMeta:
    """Метаданные версии для декоратора"""
    version: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    deprecated: bool = False
    deprecation_message: Optional[str] = None


def tool_version(
    version: str,
    input_schema: Dict[str, Any],
    output_schema: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    deprecated: bool = False,
    deprecation_message: Optional[str] = None
) -> Callable:
    """
    Декоратор для определения версии инструмента.
    
    Args:
        version: Семантическая версия (e.g., "1.0.0", "2.1.0")
        input_schema: JSON Schema для входных параметров
        output_schema: JSON Schema для выходных данных (опционально)
        description: Описание изменений в этой версии
        deprecated: Помечена ли версия как устаревшая
        deprecation_message: Сообщение об устаревании
        
    Example:
        @tool_version(
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            },
            description="Initial version with basic search"
        )
        async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
            ...
    """
    def decorator(func: Callable) -> Callable:
        # Store version metadata on the function
        func._tool_version_meta = ToolVersionMeta(
            version=version,
            input_schema=input_schema,
            output_schema=output_schema,
            description=description or func.__doc__ or "",
            deprecated=deprecated,
            deprecation_message=deprecation_message
        )
        
        @wraps(func)
        async def wrapper(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
            return await func(self, ctx, args)
        
        # Copy metadata to wrapper
        wrapper._tool_version_meta = func._tool_version_meta
        return wrapper
    
    return decorator


class VersionedTool(ABC):
    """
    Абстрактный базовый класс для версионированных инструментов.
    
    Каждый инструмент должен:
    1. Определить tool_slug, domains, name, description
    2. Определить версии через методы с декоратором @tool_version
    3. Каждая версия имеет свою input_schema и output_schema
    
    При старте воркера:
    1. Сканируются все классы, наследующие VersionedTool
    2. Извлекаются все версии из методов с @tool_version
    3. Версии регистрируются в БД как ToolBackendRelease
    """
    
    # Обязательные атрибуты класса
    tool_slug: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    
    # Опциональные атрибуты
    domains: ClassVar[List[str]] = []  # Business domains this tool serves
    requires_instance: ClassVar[bool] = False  # Требуется ли ToolInstance
    
    def __init__(self):
        self._versions: Dict[str, ToolVersionInfo] = {}
        self._collect_versions()
    
    def _collect_versions(self) -> None:
        """Собрать все версии из методов с декоратором @tool_version"""
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if hasattr(method, '_tool_version_meta'):
                meta: ToolVersionMeta = method._tool_version_meta
                self._versions[meta.version] = ToolVersionInfo(
                    version=meta.version,
                    input_schema=meta.input_schema,
                    output_schema=meta.output_schema,
                    description=meta.description or "",
                    method_name=name,
                    deprecated=meta.deprecated,
                    deprecation_message=meta.deprecation_message
                )
    
    def get_versions(self) -> List[ToolVersionInfo]:
        """Получить список всех версий инструмента"""
        return sorted(
            self._versions.values(),
            key=lambda v: self._parse_version(v.version),
            reverse=True
        )
    
    def get_version(self, version: str) -> Optional[ToolVersionInfo]:
        """Получить информацию о конкретной версии"""
        return self._versions.get(version)
    
    def get_latest_version(self) -> Optional[ToolVersionInfo]:
        """Получить последнюю версию"""
        versions = self.get_versions()
        return versions[0] if versions else None
    
    async def execute(
        self, 
        ctx: ToolContext, 
        args: Dict[str, Any],
        version: Optional[str] = None
    ) -> ToolResult:
        """
        Выполнить инструмент с указанной версией.
        
        Args:
            ctx: Контекст выполнения
            args: Аргументы вызова
            version: Версия для выполнения (если None — последняя)
            
        Returns:
            ToolResult с данными или ошибкой
        """
        if version is None:
            version_info = self.get_latest_version()
        else:
            version_info = self.get_version(version)
        
        if version_info is None:
            return ToolResult.fail(f"Version {version} not found for tool {self.tool_slug}")
        
        if version_info.deprecated:
            # Log deprecation warning but continue execution
            pass
        
        # Get the method and execute
        method = getattr(self, version_info.method_name)
        return await method(ctx, args)
    
    def validate_args(self, args: Dict[str, Any], version: Optional[str] = None) -> Optional[str]:
        """
        Валидация аргументов по input_schema версии.
        
        Returns:
            None если валидно, иначе строку с ошибкой
        """
        if version is None:
            version_info = self.get_latest_version()
        else:
            version_info = self.get_version(version)
        
        if version_info is None:
            return f"Version {version} not found"
        
        schema = version_info.input_schema
        if not schema:
            return None
        
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        
        for field_name in required:
            if field_name not in args:
                return f"Missing required field: {field_name}"
            
            field_schema = properties.get(field_name, {})
            expected_type = field_schema.get("type")
            
            if expected_type and not self._check_type(args[field_name], expected_type):
                return f"Invalid type for field '{field_name}': expected {expected_type}"
        
        return None
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Проверка типа значения"""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        return isinstance(value, expected)
    
    def to_llm_schema(self, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Преобразовать tool в формат для LLM.
        """
        if version is None:
            version_info = self.get_latest_version()
        else:
            version_info = self.get_version(version)
        
        if version_info is None:
            return {}
        
        return {
            "type": "function",
            "function": {
                "name": self.tool_slug,
                "description": self.description,
                "parameters": version_info.input_schema
            }
        }
    
    @staticmethod
    def _parse_version(version: str) -> tuple:
        """Парсинг семантической версии для сортировки"""
        try:
            parts = version.split(".")
            return tuple(int(p) for p in parts)
        except (ValueError, AttributeError):
            return (0, 0, 0)
    
    def __repr__(self) -> str:
        return f"<VersionedTool {self.tool_slug}>"


class ToolRegistry:
    """
    Реестр всех версионированных инструментов.
    Используется для регистрации и поиска инструментов.
    """
    
    _instance: Optional['ToolRegistry'] = None
    _tools: Dict[str, VersionedTool] = {}
    
    def __new__(cls) -> 'ToolRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance
    
    def register(self, tool: VersionedTool) -> None:
        """Зарегистрировать инструмент"""
        self._tools[tool.tool_slug] = tool
    
    def get(self, slug: str) -> Optional[VersionedTool]:
        """Получить инструмент по slug"""
        return self._tools.get(slug)
    
    def get_all(self) -> List[VersionedTool]:
        """Получить все зарегистрированные инструменты"""
        return list(self._tools.values())
    
    def get_by_domain(self, domain: str) -> List[VersionedTool]:
        """Получить инструменты по домену"""
        return [t for t in self._tools.values() if domain in (t.domains or [])]
    
    def clear(self) -> None:
        """Очистить реестр (для тестов)"""
        self._tools.clear()


# Global registry instance
tool_registry = ToolRegistry()


def register_tool(tool_class: type) -> type:
    """
    Декоратор класса для автоматической регистрации инструмента.
    
    Example:
        @register_tool
        class MyTool(VersionedTool):
            ...
    """
    instance = tool_class()
    tool_registry.register(instance)
    return tool_class
