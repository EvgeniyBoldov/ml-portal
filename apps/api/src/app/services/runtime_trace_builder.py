from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from app.core.logging import get_logger

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
    _logger = get_logger(__name__)
    # Legacy raw types — cleared for v3 (system not in production)
    _LEGACY_RAW_TYPES: set[str] = set()

    _CATEGORY_MAP: Dict[str, str] = {
        # lifecycle
        "run_start": "lifecycle",
        "run_end": "lifecycle",
        "orchestrator_start": "lifecycle",
        "orchestrator_end": "lifecycle",
        "planner_iteration_start": "lifecycle",
        "planner_iteration_end": "lifecycle",
        "agent_start": "lifecycle",
        "agent_end": "lifecycle",
        "synthesis_start": "lifecycle",
        "synthesis_end": "lifecycle",
        # input / decisions
        "user_request": "input",
        "routing_decision": "decision",
        "triage_complete": "decision",
        "preflight_complete": "decision",
        "intent": "intent",
        "planner_decision": "planner",
        "policy_decision": "policy",
        "confirmation_required": "policy",
        "question_answer": "system",
        "protocol_retry": "retry",
        # budget
        "budget_snapshot": "budget",
        # llm
        "llm_call": "llm",
        "llm_turn": "llm",
        "llm_request": "llm",
        "llm_response": "llm",
        "system_llm_trace": "llm",
        # operations
        "tool_call": "operation",
        "tool_result": "operation",
        # outputs / status
        "final": "final",
        "error": "error",
        "status": "system",
        "delta": "system",
        "waiting_input": "system",
        "run_paused": "system",
        "stop": "system",
        "done": "system",
    }

    _TITLES: Dict[str, str] = {
        "run_start": "Старт рантайма",
        "run_end": "Завершение рантайма",
        "orchestrator_start": "Старт оркестратора",
        "orchestrator_end": "Завершение оркестратора",
        "planner_iteration_start": "Старт итерации планера",
        "planner_iteration_end": "Завершение итерации планера",
        "agent_start": "Старт агента",
        "agent_end": "Завершение агента",
        "synthesis_start": "Старт синтеза",
        "synthesis_end": "Завершение синтеза",
        "user_request": "Запрос",
        "routing_decision": "Решение маршрутизации",
        "triage_complete": "Решение триажа",
        "preflight_complete": "Результат preflight",
        "intent": "Намерение",
        "planner_decision": "Решение планировщика",
        "policy_decision": "Решение политики",
        "confirmation_required": "Требуется подтверждение",
        "question_answer": "Вопрос-ответ",
        "protocol_retry": "Повтор протокола",
        "budget_snapshot": "Снимок бюджета",
        "llm_call": "LLM вызов",
        "llm_turn": "LLM турн",
        "llm_request": "LLM запрос",
        "llm_response": "LLM ответ",
        "system_llm_trace": "System LLM trace",
        "tool_call": "Вызов инструмента",
        "tool_result": "Результат инструмента",
        "final": "Финальный ответ",
        "error": "Ошибка",
        "status": "Статус",
        "delta": "Поток ответа",
        "waiting_input": "Ожидание ввода",
        "stop": "Остановлено",
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
        if raw_type in self._LEGACY_RAW_TYPES:
            self._logger.warning(
                "RuntimeTraceBuilder legacy raw_type=%s used; expected canonical v3 type",
                raw_type,
            )
        category = self._CATEGORY_MAP.get(raw_type)
        if category is None:
            self._logger.warning("RuntimeTraceBuilder unknown raw_type=%s; fallback to system", raw_type)
            category = "system"
        iteration = self._pick_iteration(step)
        summary = self._summary(raw_type, data)
        status = self._status(raw_type, data)
        phase = self._phase(category)
        inputs = (
            {"arguments": data.get("arguments") or data.get("parameters") or data.get("input") or data.get("payload")}
            if raw_type == "tool_call"
            else {"content": data.get("content") or data.get("request")}
            if raw_type == "user_request"
            else None
        )
        outputs = (
            {"result": data.get("result") or data.get("output") or data.get("data")}
            if raw_type == "tool_result"
            else {"content": data.get("content") or data.get("answer") or data.get("response")}
            if raw_type in {"llm_turn", "llm_response", "final_response", "final"}
            else None
        )
        decision = data if category in {"decision", "planner", "policy", "retry"} else None
        budget = data if raw_type == "budget_snapshot" else None
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
        if category == "lifecycle":
            return "system"
        if category == "input":
            return "input"
        if category == "budget":
            return "budget"
        if category == "llm":
            return "llm"
        if category in {"decision", "planner", "retry", "policy", "intent"}:
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
        if raw_type == "tool_result" and data.get("success") is False:
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
        if raw_type == "confirmation_required":
            return str(data.get("summary") or data.get("message") or "Confirmation required")
        if raw_type == "waiting_input":
            return str(data.get("question") or data.get("message") or "Waiting for input")
        if raw_type == "question_answer":
            question = str(data.get("question") or "").strip()
            answer = str(data.get("user_answer") or "").strip()
            if question and answer:
                return f"{question} → {answer}"
            if question:
                return question
            if answer:
                return answer
            return "Question answered"
        if raw_type in {"routing", "routing_decision"}:
            return str(data.get("agent_slug") or data.get("mode") or "Routing decision")
        if raw_type == "triage_complete":
            return str(data.get("decision") or data.get("status") or "Triage complete")
        if raw_type == "preflight_complete":
            return str(data.get("status") or "Preflight complete")
        if raw_type == "intent":
            return str(data.get("description") or "Intent")
        if raw_type in {"planner_action", "planner_step", "planner_decision"}:
            kind = str(data.get("kind") or data.get("action_type") or data.get("action") or "").strip()
            question = str(data.get("question") or "").strip()
            if kind in {"clarify", "ask_user"} and question:
                return question
            if kind == "thinking":
                return str(data.get("selected_action_summary") or data.get("selection_rationale") or "Thinking")
        if raw_type == "tool_call":
            return str(data.get("tool") or data.get("operation_slug") or "Tool call")
        if raw_type == "tool_result":
            status = "success" if data.get("success") is True else "failed" if data.get("success") is False else "result"
            tool_name = data.get("tool") or data.get("operation_slug") or "Tool"
            return f"{tool_name} {status}"
        if raw_type in {"llm_call", "llm_response", "llm_turn"}:
            if isinstance(data.get("parsed_response"), dict):
                selected = str(data["parsed_response"].get("selected_action_summary") or "").strip()
                if selected:
                    return selected
            purpose = str(data.get("purpose") or data.get("step_kind") or data.get("stepKind") or "").strip()
            if purpose:
                model = str(data.get("model") or data.get("provider_model") or "").strip()
                return f"{purpose} · {model}" if model else purpose
            metric = data.get("tokens_out", data.get("response_length"))
            if metric is not None:
                return f"tokens_out={metric}"
            model = str(data.get("model") or data.get("provider_model") or "").strip()
            return f"model={model}" if model else "LLM"
        if raw_type == "budget_snapshot":
            owner = data.get("owner_scope") or data.get("scope") or "unknown"
            return f"{owner}: snapshot"
        if raw_type == "final":
            return str(data.get("content") or data.get("answer") or "Final response")
        if raw_type == "error":
            return str(data.get("error") or data.get("message") or "Error")
        return str(data)[:180] if data else raw_type
