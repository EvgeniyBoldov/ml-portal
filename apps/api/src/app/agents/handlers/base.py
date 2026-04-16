"""
Базовый класс для Tool Handlers
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, ClassVar

from app.agents.context import ToolContext, ToolResult
from app.core.schema_hash import compute_schema_hash as _compute_hash


class ToolHandler(ABC):
    """
    Абстрактный базовый класс для всех tool handlers.
    
    Каждый tool должен:
    1. Определить slug, name, description
    2. Определить domains для runtime grouping
    3. Определить input_schema (JSON Schema для аргументов)
    4. Реализовать execute()
    
    Пример:
        class MyTool(ToolHandler):
            slug = "my.tool"
            name = "My Tool"
            description = "Does something useful"
            input_schema = {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
            
            async def execute(self, ctx, args):
                result = do_something(args["query"])
                return ToolResult.ok({"result": result})
    """
    
    slug: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    domains: ClassVar[List[str]] = []  # Business domains this tool serves
    input_schema: ClassVar[Dict[str, Any]]
    output_schema: ClassVar[Optional[Dict[str, Any]]] = None
    
    @abstractmethod
    async def execute(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        """
        Выполнить tool с заданными аргументами.
        
        Args:
            ctx: Контекст выполнения (tenant, user, scopes)
            args: Аргументы, валидированные по input_schema
            
        Returns:
            ToolResult с данными или ошибкой
        """
        pass
    
    def validate_args(self, args: Dict[str, Any]) -> Optional[str]:
        """
        Валидация аргументов по input_schema.
        Возвращает None если валидно, иначе строку с ошибкой.
        
        По умолчанию проверяет только required поля.
        Можно переопределить для более строгой валидации.
        """
        schema = self.input_schema
        if not schema:
            return None
        
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        
        for field in required:
            if field not in args:
                return f"Missing required field: {field}"
            
            field_schema = properties.get(field, {})
            expected_type = field_schema.get("type")
            
            if expected_type and not self._check_type(args[field], expected_type):
                return f"Invalid type for field '{field}': expected {expected_type}"
        
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
    
    @property
    def schema_hash(self) -> str:
        """SHA256 hash of input_schema + output_schema for observability"""
        return _compute_hash(self.input_schema, self.output_schema)
    
    def to_llm_schema(self) -> Dict[str, Any]:
        """
        Преобразовать tool в формат для LLM (JSON в промпте).
        """
        return {
            "type": "function",
            "function": {
                "name": self.slug,
                "description": self.description,
                "parameters": self.input_schema
            }
        }

    def to_mcp_descriptor(self) -> Dict[str, Any]:
        """
        Экспортировать локальную операцию в MCP-compatible descriptor format.
        """
        return {
            "name": self.slug,
            "description": self.description,
            "inputSchema": self.input_schema or {"type": "object", "properties": {}, "required": []},
            "outputSchema": self.output_schema,
            "domains": self.domains or [],
        }
    
    def __repr__(self) -> str:
        return f"<ToolHandler {self.slug}>"
