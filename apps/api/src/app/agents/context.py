"""
Контексты выполнения для Agent Runtime
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import uuid


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
    
    def to_message_content(self) -> str:
        """Преобразовать результат в текст для LLM"""
        if self.success:
            import json
            return json.dumps(self.data, ensure_ascii=False, indent=2)
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
