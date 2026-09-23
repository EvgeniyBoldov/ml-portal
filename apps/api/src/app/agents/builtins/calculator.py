"""A small, side-effect-free arithmetic calculator for agents."""
from __future__ import annotations

import ast
import math
from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"expression": {"type": "string", "description": "Arithmetic expression using numbers, +, -, *, /, //, %, **, and parentheses."}},
    "required": ["expression"],
    "additionalProperties": False,
}
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"expression": {"type": "string"}, "result": {"type": "number"}},
}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = float(node.value)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand)
        if isinstance(node.op, ast.USub):
            value = -value
    elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent magnitude must be at most 100")
        value = _BINARY[type(node.op)](left, right)
    else:
        raise ValueError("Only basic arithmetic expressions are supported")
    if not math.isfinite(value):
        raise ValueError("Result must be finite")
    return value


_BINARY = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}


@register_tool
class CalculatorTool(VersionedTool):
    tool_slug: ClassVar[str] = "calculator"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Calculator"
    description: ClassVar[str] = "Evaluate a basic arithmetic expression safely, without executing code."

    @tool_version(version="1.0.0", input_schema=_INPUT_SCHEMA, output_schema=_OUTPUT_SCHEMA,
                  description="Evaluate a basic arithmetic expression")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        expression = str(args.get("expression") or "").strip()
        if not expression or len(expression) > 500:
            return ToolResult.fail("Expression must contain 1 to 500 characters.")
        try:
            result = _evaluate(ast.parse(expression, mode="eval"))
        except (SyntaxError, ValueError, ArithmeticError, OverflowError) as exc:
            return ToolResult.fail(f"Invalid arithmetic expression: {exc}")
        rendered: int | float = int(result) if result.is_integer() else result
        return ToolResult.ok(data={"expression": expression, "result": rendered}, message=str(rendered))
