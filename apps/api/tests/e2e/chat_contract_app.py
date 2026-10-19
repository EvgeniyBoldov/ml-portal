"""Isolated E2E app: real chat HTTP/services/DB/storage, scripted runtime events.

Never imported by app.main. Run only in a separate process/port with
CHAT_CONTRACT_E2E=1. Production LLM quality is exercised by the live suite.
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

if os.environ.get("CHAT_CONTRACT_E2E") != "1":
    raise RuntimeError("This test application requires CHAT_CONTRACT_E2E=1")

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.main import app
from app.runtime.contracts import PipelineRequest
from app.runtime.events import RuntimeEvent
from app.runtime.pipeline import RuntimePipeline, _build_continuation_state, _extract_effective_goal
from app.services.chat_turn_orchestrator import ChatTurnOrchestrator


async def no_compaction(self, **kwargs):
    pass


async def scripted_execute(self, request: PipelineRequest, ctx) -> AsyncIterator[RuntimeEvent]:
    checkpoint = (request.continuation_meta or {}).get("resume_checkpoint")
    continuation = _build_continuation_state(request, checkpoint)
    goal = _extract_effective_goal(request, checkpoint)
    mode = goal.split()[0].removeprefix("E2E:")
    run_id = str(request.runtime_run_id)
    yield RuntimeEvent.run_start(run_id=run_id)
    if mode in {"clarify", "clarify-three", "clarify-confirm", "file-clarify", "clarify-batch"}:
        questions = ["Какой проект?", "Какой период?", "В каком формате нужен ответ?"]
        if mode == "clarify-batch":
            questions = ["Какой проект?\nКакой период?"]
        rounds = 3 if mode == "clarify-three" else 1
        history = continuation.get("clarification_history", [])
        if len(history) < rounds:
            question = questions[len(history)]
            yield RuntimeEvent.stop("waiting_input", run_id=run_id, question=question,
                context={"question": question, "original_goal": goal, "clarification_history": history})
            return
        if mode == "clarify-confirm" and continuation.get("resume_action") != "confirm":
            yield RuntimeEvent.stop("waiting_confirmation", run_id=run_id,
                question="Подтвердить публикацию отчёта?", action={"operation_fingerprint": "e2e-safe-confirm",
                    "summary": "Публикация тестового отчёта", "risk_level": "write"},
                context={"question": "Подтвердить публикацию отчёта?", "original_goal": goal,
                    "clarification_history": history})
            return
        if mode == "file-clarify":
            assert any(item.is_current for item in request.attachments), "Original file focus lost on resume"
        answer = "Готово: " + "; ".join(f'{h["question"]} {h["answer"]}' for h in history)
    elif mode == "confirm":
        if continuation.get("resume_action") != "confirm":
            yield RuntimeEvent.stop("waiting_confirmation", run_id=run_id,
                question="Подтвердить тестовое действие?", action={"operation_fingerprint": "e2e-safe-confirm",
                    "summary": "Тестовое действие", "risk_level": "write"},
                context={"question": "Подтвердить тестовое действие?", "original_goal": goal})
            return
        assert request.confirmation_tokens, "Missing issued confirmation token"
        answer = "Действие подтверждено"
    elif mode == "runtime-error":
        yield RuntimeEvent.error("SECRET_INTERNAL_ERROR", error_code="provider_unavailable", retryable=True)
        return
    elif mode == "empty-agent":
        # Reproduce a runtime that stops without a final answer or an error;
        # ChatTurnOrchestrator must surface its generic empty-response error.
        return
    elif mode == "exception":
        raise RuntimeError("SECRET_INTERNAL_EXCEPTION")
    elif mode == "slow":
        yield RuntimeEvent.delta("Начало длинного ответа")
        await asyncio.sleep(30)
        answer = "ЗАПОЗДАЛЫЙ_ОТВЕТ"
    elif mode == "files":
        from app.services.chat_attachment_service import ChatAttachmentService
        artifact = await ChatAttachmentService(self._session).create_generated_attachment(
            chat_id=request.chat_id, owner_id=request.user_id, filename="e2e-result.txt",
            content=b"E2E generated result 7391", content_type="text/plain")
        yield RuntimeEvent.final("Готов файл. [Документация](https://example.com/report)", run_id=run_id,
            attachments=[artifact])
        return
    elif mode in {"synthesis-file", "synthesis-file-fail"}:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from uuid import UUID
        from app.runtime.synthesizer import Synthesizer
        from app.runtime.synthesis_files import FileSynthesisOutput
        from app.runtime.turn_state import RuntimeTurnState
        from app.runtime.run_context import RunContext
        state = RuntimeTurnState(run_id=UUID(run_id), chat_id=UUID(request.chat_id),
            user_id=UUID(request.user_id), tenant_id=UUID(request.tenant_id), goal=goal,
            current_user_query=goal, attachment_contexts=request.attachments,
            run_context=RunContext(original_request=goal, goal=goal))
        result = SimpleNamespace(value=FileSynthesisOutput(message="Готов файл примера.", files=[{
            "filename": "example.py", "format": "py", "content": "print('SYNTHESIS_FILE_7391')\n"}]))
        with patch("app.runtime.synthesis_files.StructuredLLMCall") as llm:
            llm.return_value.invoke = AsyncMock(return_value=result)
            if mode == "synthesis-file-fail":
                llm.return_value.invoke.side_effect = ValueError("E2E_PRIVATE_FILE_ERROR")
            async for event in Synthesizer(session=self._session, llm_client=self._llm_client).stream(
                runtime_state=state, run_id=state.run_id, ctx=ctx, synthesis_context={
                    "user_question": goal, "synthesis_brief": {"delivery": "text_and_files", "content_mode": "generative",
                        "files": [{"filename": "example.py", "format": "py"}]},
                    "direct_answer_draft": "Create the requested Python example.",
                    "run_context": state.run_context.projection(), "artifacts": [], "sources": []}):
                yield event
        if state.final_answer:
            await self._apply_chat_context_outcome(request=request, runtime_state=state, branch_id=None,
                terminal_state="completed", project_context={})
        return
    elif mode == "read-existing":
        from app.agents.builtins.file_read import FileReadTool
        assert request.attachments, "Previous generated artifact missing"
        result = await FileReadTool().v1_0_0(ctx, {"artifact_id": request.attachments[-1].ref.artifact_id})
        assert result.success, str(result)
        answer = str(result.data["content"])
    elif mode == "read":
        from app.agents.builtins.file_read import FileReadTool
        current = [item for item in request.attachments if item.is_current]
        assert current, "Current attachment missing"
        result = await FileReadTool().v1_0_0(ctx, {"artifact_id": current[-1].ref.artifact_id})
        assert result.success, str(result)
        answer = str(result.data["content"])
    else:
        answer = f"Получено {len(request.request_text)} символов: {request.request_text[:120]}"
    yield RuntimeEvent.delta(answer[:8])
    await asyncio.sleep(0.05)
    yield RuntimeEvent.delta(answer[8:])
    yield RuntimeEvent.final(answer, run_id=run_id)


@app.middleware("http")
async def wire_faults(request: Request, call_next):
    if request.method == "POST" and request.url.path.endswith("/messages"):
        body = await request.json()
        mode = str(body.get("content", "")).split()[0]
        if mode.startswith("E2E:http-"):
            status = int(mode.rsplit("-", 1)[1])
            return JSONResponse({"detail": f"Тестовая ошибка HTTP {status}"}, status_code=status)
        if mode == "E2E:broken-sse":
            return StreamingResponse(iter(["event: delta\ndata: Незавершённый ответ\n\n"]), media_type="text/event-stream")
        if mode == "E2E:malformed-sse":
            return StreamingResponse(iter(["event: pause\ndata: {invalid}\n\n"]), media_type="text/event-stream")
    return await call_next(request)


RuntimePipeline.execute = scripted_execute
ChatTurnOrchestrator._dispatch_context_compaction = no_compaction

# The deterministic suite drives hundreds of requests in seconds; actual 429
# UI behavior is covered by wire_faults. Leave production throttling untouched.
from app.core.config import get_settings
get_settings().GLOBAL_RATE_LIMIT_ENABLED = False
async def no_rate_limit():
    pass

def override_rate_limits(dependant):
    call = dependant.call
    if getattr(call, "__module__", "") == "app.api.deps" and getattr(call, "__name__", "") == "_check":
        app.dependency_overrides[call] = no_rate_limit
    for dependency in dependant.dependencies:
        override_rate_limits(dependency)
for route in app.routes:
    if hasattr(route, "dependant"):
        override_rate_limits(route.dependant)

@app.get("/api/v1/__e2e/chats/{chat_id}/turns")
async def inspect_turns(chat_id: str):
    from sqlalchemy import text
    from app.core.db import get_session_factory
    async with get_session_factory()() as session:
        rows = (await session.execute(text(
            "select status, user_message_id, assistant_message_id from chat_turns where chat_id=cast(:chat as uuid) order by started_at"
        ), {"chat": chat_id})).mappings()
        return [dict(row) for row in rows]
