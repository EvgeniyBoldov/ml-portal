"""
Контексты выполнения для Agent Runtime
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid


# ─────────────────────────────────────────────────────────────────────────────
# TOOL LOGGER
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolLogEntry:
    """Single structured log entry from a tool execution."""
    level: str  # debug, info, warning, error
    message: str
    elapsed_ms: int = 0
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "level": self.level,
            "message": self.message,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.data:
            d["data"] = self.data
        return d


class ToolLogger:
    """
    Structured logger for tool executions.

    Collects log entries inside a tool's execute() method so they can be
    persisted alongside the tool_result step in RunStore.

    Usage inside a ToolHandler:
        async def execute(self, ctx: ToolContext, args: Dict) -> ToolResult:
            log = ctx.tool_logger("rag.search")
            log.info("Starting search", query=args["query"])

            try:
                results = await service.search(...)
                log.info("Found results", count=len(results))
            except Exception as e:
                log.error("Search failed", error=str(e))
                return ToolResult.fail(str(e), logs=log.entries_dict())

            return ToolResult.ok({"hits": results}, logs=log.entries_dict())

    The runtime will automatically pick up metadata["logs"] and store it
    in the tool_result step data.
    """

    def __init__(self, tool_slug: str):
        self.tool_slug = tool_slug
        self._entries: List[ToolLogEntry] = []
        self._start = time.monotonic()

    def _elapsed(self) -> int:
        return int((time.monotonic() - self._start) * 1000)

    def _add(self, level: str, message: str, **data: Any) -> None:
        self._entries.append(ToolLogEntry(
            level=level,
            message=message,
            elapsed_ms=self._elapsed(),
            data=data if data else None,
        ))

    def debug(self, message: str, **data: Any) -> None:
        self._add("debug", message, **data)

    def info(self, message: str, **data: Any) -> None:
        self._add("info", message, **data)

    def warning(self, message: str, **data: Any) -> None:
        self._add("warning", message, **data)

    def error(self, message: str, **data: Any) -> None:
        self._add("error", message, **data)

    def has_errors(self) -> bool:
        return any(e.level == "error" for e in self._entries)

    def entries_dict(self) -> List[Dict[str, Any]]:
        """Serialize entries for storage in ToolResult.metadata["logs"]."""
        return [e.to_dict() for e in self._entries]

    @property
    def total_ms(self) -> int:
        return self._elapsed()

    def __repr__(self) -> str:
        return f"<ToolLogger {self.tool_slug} entries={len(self._entries)}>"


# ─────────────────────────────────────────────────────────────────────────────
# TOOL CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolContext:
    """
    Контекст, передаваемый в каждый tool при выполнении.
    Содержит информацию о tenant, user, chat и RBAC scopes.
    """
    tenant_id: str
    user_id: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chat_id: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    denied_reasons: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def tool_logger(self, tool_slug: str) -> ToolLogger:
        """Create a ToolLogger scoped to a specific tool execution."""
        return ToolLogger(tool_slug)
    
    def with_extra(self, **kwargs) -> ToolContext:
        """Создать копию контекста с дополнительными данными"""
        new_extra = {**self.extra, **kwargs}
        return ToolContext(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            request_id=self.request_id,
            chat_id=self.chat_id,
            scopes=self.scopes.copy(),
            extra=new_extra
        )


@dataclass
class ToolResult:
    """
    Результат выполнения tool.
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ok(cls, data: Dict[str, Any], **metadata) -> ToolResult:
        """Успешный результат"""
        return cls(success=True, data=data, metadata=metadata)
    
    @classmethod
    def fail(cls, error: str, **metadata) -> ToolResult:
        """Ошибка выполнения"""
        return cls(success=False, error=error, metadata=metadata)
    
    def to_message_content(self, max_chars: int = 4000) -> str:
        """Преобразовать результат в текст для LLM с ограничением размера"""
        if self.success:
            import json
            text = json.dumps(self.data, ensure_ascii=False, indent=2)
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... [truncated, total {len(text)} chars]"
            return text
        else:
            return f"Error: {self.error}"


@dataclass
class ToolCall:
    """
    Запрос на вызов tool от LLM.
    """
    id: str
    tool_slug: str
    arguments: Dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolCall:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            tool_slug=data["tool"],
            arguments=data.get("arguments", {})
        )


@dataclass
class RunStep:
    """
    Один шаг выполнения агента (для трейсинга и персистентности).
    """
    step_id: str
    step_type: str  # "llm_request", "tool_call", "tool_result", "final"
    timestamp: datetime
    data: Dict[str, Any]
    
    @classmethod
    def create(cls, step_type: str, data: Dict[str, Any]) -> RunStep:
        return cls(
            step_id=str(uuid.uuid4()),
            step_type=step_type,
            timestamp=datetime.now(timezone.utc),
            data=data
        )


@dataclass
class RunContext:
    """
    Контекст выполнения агента (in-memory state).
    Может быть расширен для персистентности (RunStore).
    """
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[RunStep] = field(default_factory=list)
    tool_calls_count: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def add_message(self, role: str, content: str, **extra) -> None:
        """Добавить сообщение в историю"""
        msg = {"role": role, "content": content, **extra}
        self.messages.append(msg)
    
    def add_step(self, step_type: str, data: Dict[str, Any]) -> RunStep:
        """Добавить шаг выполнения"""
        step = RunStep.create(step_type, data)
        self.steps.append(step)
        return step
    
    def increment_tool_calls(self) -> int:
        """Увеличить счётчик вызовов tools"""
        self.tool_calls_count += 1
        return self.tool_calls_count
