from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from app.schemas.runtime_trace import (
    RawEventRefResponse,
    RunTraceResponse,
    SemanticEventResponse,
    TraceIterationResponse,
)


@dataclass
class TraceStep:
    id: str
    raw_type: str
    data: Dict[str, Any]
    step_number: Optional[int] = None
    created_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class RuntimeTraceBuilder:
    _CATEGORY_MAP: Dict[str, str] = {
        "user_request": "input",
        "budget_init": "budget",
        "budget_policy": "budget",
        "budget_consumed": "budget",
        "budget_limit_exceeded": "budget",
        "budget_check": "budget",
        "budget": "budget",
        "llm_call": "llm",
        "llm_request": "llm",
        "llm_response": "llm",
        "routing": "decision",
        "triage": "decision",
        "protocol_retry": "retry",
        "planner_action": "planner",
        "planner_step": "planner",
        "intent": "planner",
        "operation_call": "operation",
        "tool_call": "operation",
        "operation_result": "operation",
        "tool_result": "operation",
        "policy_decision": "policy",
        "confirmation_required": "policy",
        "final": "final",
        "final_response": "final",
        "error": "error",
        "status": "system",
        "thinking": "system",
        "delta": "system",
        "waiting_input": "system",
        "run_paused": "system",
        "stop": "system",
        "done": "system",
    }

    _TITLES: Dict[str, str] = {
        "user_request": "Запрос",
        "budget_policy": "Лимиты",
        "budget_consumed": "Расход лимитов",
        "llm_call": "LLM вызов",
        "llm_request": "LLM запрос",
        "llm_response": "LLM ответ",
        "routing": "Маршрутизация",
        "protocol_retry": "Повтор протокола",
        "operation_call": "Вызов операции",
        "tool_call": "Вызов операции",
        "operation_result": "Результат операции",
        "tool_result": "Результат операции",
        "planner_action": "Планировщик",
        "planner_step": "Планировщик",
        "intent": "Интент",
        "policy_decision": "Решение политики",
        "confirmation_required": "Требуется подтверждение",
        "final": "Финальный ответ",
        "final_response": "Финальный ответ",
        "error": "Ошибка",
    }

    def build(self, steps: Iterable[TraceStep]) -> RunTraceResponse:
        events = [self._normalize(step) for step in steps]
        buckets: dict[int, list[SemanticEventResponse]] = defaultdict(list)
        for event in events:
            buckets[event.iteration].append(event)
        iterations = [
            TraceIterationResponse(index=index, events=buckets[index])
            for index in sorted(buckets.keys())
        ]
        return RunTraceResponse(iterations=iterations, total_events=len(events))

    def _normalize(self, step: TraceStep) -> SemanticEventResponse:
        raw_type = step.raw_type
        data = step.data or {}
        category = self._CATEGORY_MAP.get(raw_type, "system")
        iteration = self._pick_iteration(step)
        summary = self._summary(raw_type, data)
        status = self._status(raw_type, data)
        phase = self._phase(category)
        inputs = (
            {"arguments": data.get("arguments") or data.get("parameters") or data.get("input") or data.get("payload")}
            if raw_type in {"operation_call", "tool_call"}
            else {"content": data.get("content") or data.get("request")}
            if raw_type == "user_request"
            else None
        )
        outputs = (
            {"result": data.get("result") or data.get("output") or data.get("data")}
            if raw_type in {"operation_result", "tool_result"}
            else {"content": data.get("content") or data.get("answer") or data.get("response")}
            if raw_type in {"llm_response", "final_response", "final"}
            else None
        )
        decision = data if category in {"decision", "planner", "policy", "retry"} else None
        budget = (
            data.get("budget")
            if isinstance(data.get("budget"), dict)
            else data
            if raw_type.startswith("budget_")
            else None
        )
        refs = data.get("refs") if isinstance(data.get("refs"), dict) else None
        return SemanticEventResponse(
            id=step.id,
            raw_type=raw_type,
            category=category,
            title=self._TITLES.get(raw_type, f"{category}: {raw_type}"),
            summary=summary,
            status=status,
            phase=phase,
            iteration=iteration,
            started_at=step.created_at,
            duration_ms=step.duration_ms,
            inputs=inputs,
            outputs=outputs,
            decision=decision,
            budget=budget,
            refs=refs,
            raw=RawEventRefResponse(id=step.id, raw_type=raw_type, raw=data),
        )

    @staticmethod
    def _pick_iteration(step: TraceStep) -> int:
        data = step.data or {}
        direct = data.get("iteration", data.get("step"))
        if isinstance(direct, int) and direct >= 0:
            return direct
        env = data.get("_envelope")
        if isinstance(env, dict):
            sequence = env.get("sequence")
            if isinstance(sequence, int) and sequence >= 0:
                return sequence
        if isinstance(step.step_number, int):
            return step.step_number
        return 0

    @staticmethod
    def _phase(category: str) -> str:
        if category == "input":
            return "input"
        if category == "budget":
            return "budget"
        if category == "llm":
            return "llm"
        if category in {"decision", "planner", "retry", "policy"}:
            return "decision"
        if category == "operation":
            return "operation"
        if category in {"final", "error"}:
            return "final"
        return "system"

    @staticmethod
    def _status(raw_type: str, data: Dict[str, Any]) -> str:
        if raw_type == "error":
            return "error"
        if raw_type in {"protocol_retry", "confirmation_required"}:
            return "warn"
        if raw_type in {"operation_result", "tool_result"} and data.get("success") is False:
            return "error"
        if raw_type in {"final", "final_response"}:
            return "ok"
        return "info"

    @staticmethod
    def _summary(raw_type: str, data: Dict[str, Any]) -> str:
        if raw_type == "user_request":
            return str(data.get("content") or data.get("request") or "User request")
        if raw_type == "protocol_retry":
            return str(data.get("reason") or "Protocol retry")
        if raw_type == "routing":
            return str(data.get("agent_slug") or data.get("mode") or "Routing decision")
        if raw_type == "intent":
            return str(data.get("description") or "Intent")
        if raw_type in {"operation_call", "tool_call"}:
            return str(data.get("operation_slug") or data.get("tool") or data.get("operation") or "Operation call")
        if raw_type in {"operation_result", "tool_result"}:
            status = "success" if data.get("success") is True else "failed" if data.get("success") is False else "result"
            op = data.get("operation_slug") or data.get("tool") or data.get("operation") or "Operation"
            return f"{op} {status}"
        if raw_type in {"llm_call", "llm_response"}:
            return f"response_length={data.get('response_length') or data.get('tokens_out') or 'n/a'}"
        if raw_type == "budget_consumed":
            return f"used={data.get('consumed') or data.get('used') or data.get('steps_used') or 'n/a'}"
        if raw_type in {"final", "final_response"}:
            return str(data.get("content") or data.get("answer") or "Final response")
        if raw_type == "error":
            return str(data.get("error") or data.get("message") or "Error")
        return str(data)[:180] if data else raw_type
