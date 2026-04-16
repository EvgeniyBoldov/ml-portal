"""
Контексты выполнения для Agent Runtime
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from dataclasses import fields as dataclass_fields
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
            log = ctx.tool_logger("collection.search")
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
class RuntimeDependencies:
    """Typed runtime dependencies passed through ToolContext."""

    session_factory: Any = None
    operation_executor: Any = None
    execution_graph: Any = None
    sandbox_overrides: Dict[str, Any] = field(default_factory=dict)
    helper_summary: Optional[Dict[str, Any]] = None
    execution_outline: Optional[Dict[str, Any]] = None
    runtime_trace_logger: Any = None


@dataclass
class ToolContext:
    """
    Контекст, передаваемый в каждый tool при выполнении.
    Содержит информацию о tenant, user, chat и RBAC scopes.
    """
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chat_id: Optional[uuid.UUID] = None
    scopes: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    denied_reasons: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tenant_id = self._to_uuid(self.tenant_id, "tenant_id")
        self.user_id = self._to_uuid(self.user_id, "user_id")
        if self.chat_id is not None:
            self.chat_id = self._to_uuid(self.chat_id, "chat_id")

    @staticmethod
    def _to_uuid(value: Any, field_name: str) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except Exception:
            # Backward-compat: legacy code may still pass non-UUID identifiers.
            return uuid.uuid5(uuid.NAMESPACE_URL, f"{field_name}:{value}")

    def tool_logger(self, tool_slug: str) -> ToolLogger:
        """Create a ToolLogger scoped to a specific tool execution."""
        return ToolLogger(tool_slug)

    def get_runtime_deps(self) -> RuntimeDependencies:
        raw = self.extra.get("runtime_deps")
        if isinstance(raw, RuntimeDependencies):
            return raw
        if isinstance(raw, dict):
            allowed = {item.name for item in dataclass_fields(RuntimeDependencies)}
            normalized = {key: value for key, value in raw.items() if key in allowed}
            deps = RuntimeDependencies(**normalized)
        else:
            deps = RuntimeDependencies()

        # Backward-compatible hydration from legacy extra keys.
        deps.session_factory = deps.session_factory or self.extra.get("session_factory")
        deps.operation_executor = deps.operation_executor or self.extra.get("operation_executor")
        deps.execution_graph = deps.execution_graph or self.extra.get("execution_graph")
        deps.sandbox_overrides = deps.sandbox_overrides or dict(self.extra.get("sandbox_overrides") or {})
        if deps.helper_summary is None:
            helper_summary = self.extra.get("helper_summary")
            deps.helper_summary = helper_summary if isinstance(helper_summary, dict) else None
        if deps.execution_outline is None:
            execution_outline = self.extra.get("execution_outline")
            deps.execution_outline = execution_outline if isinstance(execution_outline, dict) else None
        deps.runtime_trace_logger = deps.runtime_trace_logger or self.extra.get("runtime_trace_logger")
        self.set_runtime_deps(deps)
        return deps

    def set_runtime_deps(self, deps: RuntimeDependencies) -> None:
        self.extra["runtime_deps"] = deps
        # Keep legacy aliases for compatibility until full cleanup.
        self.extra["session_factory"] = deps.session_factory
        self.extra["operation_executor"] = deps.operation_executor
        self.extra["execution_graph"] = deps.execution_graph
        self.extra["sandbox_overrides"] = deps.sandbox_overrides
        if deps.helper_summary is not None:
            self.extra["helper_summary"] = deps.helper_summary
        if deps.execution_outline is not None:
            self.extra["execution_outline"] = deps.execution_outline
        if deps.runtime_trace_logger is not None:
            self.extra["runtime_trace_logger"] = deps.runtime_trace_logger

    def with_runtime_deps(self, **kwargs: Any) -> ToolContext:
        deps = self.get_runtime_deps()
        for key, value in kwargs.items():
            if hasattr(deps, key):
                setattr(deps, key, value)
        self.set_runtime_deps(deps)
        return self
    
    def with_extra(self, **kwargs) -> ToolContext:
        """Создать копию контекста с дополнительными данными"""
        new_extra = {**self.extra, **kwargs}
        ctx = ToolContext(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            request_id=self.request_id,
            chat_id=self.chat_id,
            scopes=self.scopes.copy(),
            denied_tools=self.denied_tools.copy(),
            denied_reasons=self.denied_reasons.copy(),
            extra=new_extra
        )
        # Re-hydrate runtime deps to preserve typed view.
        ctx.get_runtime_deps()
        return ctx


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
class OperationCall:
    """
    Запрос на вызов operation от LLM.
    """
    id: str
    operation_slug: str
    arguments: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OperationCall:
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            operation_slug=data["operation"],
            arguments=data.get("arguments", {})
        )
