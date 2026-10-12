"""Bounded user-facing finalization after execution stops unexpectedly."""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import get_logger
from app.runtime.budgets import BudgetRegistry, RunLimits
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.redactor import RuntimeRedactor
from app.runtime.synthesis_context import SynthesisContextBuilder
from app.runtime.turn_state import RuntimeTurnState

logger = get_logger(__name__)


def limitation_message(code: str) -> str:
    value = code.casefold()
    if any(word in value for word in ("credential", "authentication", "unauthorized", "401", "учётных данных", "учетных данных")):
        return "Часть данных недоступна: отсутствуют или не действуют учётные данные для источника."
    if any(word in value for word in ("access_denied", "access denied", "permission", "forbidden", "403", "нет доступа", "доступ запрещ")):
        return "Часть данных недоступна: недостаточно прав доступа к источнику."
    if any(word in value for word in ("timeout", "timed out", "wall_time", "time_limit")):
        return "Обработка запроса заняла слишком много времени; полный результат получить не удалось."
    if any(word in value for word in ("limit", "budget", "max_llm_calls", "max_tool_calls", "max_retries", "context_window_exceeded")):
        return "Достигнут лимит выполнения запроса; часть работы осталась незавершённой."
    return "Не удалось завершить обработку запроса; полный результат пока не получен."


def _safe_reports(value: Any) -> Any:
    if isinstance(value, list):
        return [_safe_reports(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe_reports(item) for key, item in value.items() if key not in {
            "diagnostics", "error", "error_code", "reason_code", "traceback", "debug", "operator_message",
        }}
    return value


def partial_context(*, plan: dict[str, Any], state: RuntimeTurnState,
                    failure_code: str, max_chars: int = 120_000) -> dict[str, Any]:
    message = limitation_message(failure_code)
    context = SynthesisContextBuilder(max_chars=max_chars).build_partial(
        plan=plan, message=message, deleted_artifact_ids=list(state.deleted_artifact_ids))
    safe_limitations = [{"message": message}]
    for item in context.get("limitations", []):
        safe_limitations.append({"task_id": item.get("task_id"),
                                 "message": limitation_message(str(item.get("reason_code") or ""))})
    reports = _safe_reports(context.get("completed_task_reports", []))
    for report in reports:
        if report.get("status") == "failed":
            report["description"] = report["answer"] = "Эта часть запроса не выполнена."
    context["completed_task_reports"] = reports
    context["resolution_decisions"] = []
    context["limitations"] = safe_limitations
    for item in state.execution_limitations:
        safe_limitations.append({"message": limitation_message(item.get("code", ""))})
    # Successful direct memory receipts are evidence, even if the agent failed
    # before declaring a task result. Never re-query or execute tools here.
    for entry in state.tool_ledger.entries:
        if entry.success and entry.operation.endswith("memory.search") and isinstance(entry.result_data, dict):
            data = entry.result_data
            if isinstance(data.get("items"), list):
                context["memory_context"].append({"type": "memory_recall", "relevant_knowledge": data["items"]})
        elif entry.success is False:
            safe_limitations.append({"message": limitation_message(entry.result_preview or "")})
    context["limitations"] = list({item["message"]: item for item in safe_limitations}.values())
    context["execution_summary"] = {"partial": True, "message": message}
    return SynthesisContextBuilder(max_chars=max_chars)._compact_to_limit(RuntimeRedactor().redact(context))


async def stream_partial_answer(*, synthesizer: Any, plan: dict[str, Any],
                                runtime_state: RuntimeTurnState, failure_code: str,
                                planner_kwargs: dict[str, Any]) -> AsyncIterator[RuntimeEvent]:
    """One finalization attempt, with a separate finite budget and safe fallback."""
    settings = get_settings()
    timeout = settings.RUNTIME_FINALIZATION_TIMEOUT_SECONDS
    message = limitation_message(failure_code)
    runtime_state.final_answer = None
    runtime_state.final_error = None
    notices = [message, *[limitation_message(item.get("code", "")) for item in runtime_state.execution_limitations]]
    try:
        context = partial_context(plan=plan, state=runtime_state, failure_code=failure_code,
                                  max_chars=int(planner_kwargs.get("synthesis_context_max_chars") or 120_000))
        notices = list(dict.fromkeys(item["message"] for item in context["limitations"]))
        reserve = BudgetRegistry(run_limits=RunLimits(llm_calls=1, retries=0, wall_time_ms=timeout * 1000))
        buffered: list[RuntimeEvent] = []
        async with asyncio.timeout(timeout):
            async for event in synthesizer.stream(
                runtime_state=runtime_state, run_id=UUID(str(plan["root_run_id"])), synthesis_context=context,
                model=planner_kwargs.get("model"), platform_config=planner_kwargs.get("platform_config"),
                sandbox_overrides=planner_kwargs.get("sandbox_overrides"),
                logging_level=planner_kwargs.get("logging_level"), budget_registry=reserve,
                budget_resolver=planner_kwargs.get("budget_resolver"),
            ):
                if event.type in {RuntimeEventType.DELTA, RuntimeEventType.FINAL}:
                    buffered.append(event)
                elif event.type == RuntimeEventType.ERROR:
                    notices.append(limitation_message(str(event.data.get("error_code") or event.data.get("error") or "")))
                elif event.type != RuntimeEventType.ERROR:
                    yield event
        if runtime_state.final_answer and any(event.type == RuntimeEventType.FINAL for event in buffered):
            additions = [notice for notice in dict.fromkeys(notices) if notice not in runtime_state.final_answer]
            if additions:
                runtime_state.final_answer += "\n\n" + "\n".join(additions)
            runtime_state.final_error = None
            for event in buffered:
                if event.type == RuntimeEventType.FINAL:
                    event.data["content"] = runtime_state.final_answer
                yield event
            return
    except TimeoutError:
        notices.append(limitation_message("finalization_timeout"))
        logger.warning("Partial answer synthesis exceeded its finalization reserve")
    except Exception:
        logger.exception("Partial answer synthesis failed")
    runtime_state.final_error = None
    runtime_state.final_answer = "\n".join(dict.fromkeys(notices))
    yield RuntimeEvent.final(runtime_state.final_answer, sources=[], run_id=str(plan["root_run_id"]), attachments=[])
