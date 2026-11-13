"""
Synthesizer — streams the final answer for one terminal synthesis checkpoint.

Its only factual input is the runtime-owned context built from the completed
tasks of the final persisted plan.

Output: a stream of DELTA events followed by a FINAL event carrying full text
and accumulated sources. This is the only place in runtime that directly
streams text to the user for orchestrated runs.

"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.budgets import BudgetRegistry, BudgetResolver
from app.runtime.context_snapshot import compact_snapshot, prompt_snapshot, serialize_limits
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.input_builders import SynthesizerInputBuilder
from app.runtime.llm.streaming import RoleStreamingCall, StreamDelta, StreamError, StreamTurn, StreamContext
from app.adapters.impl.llm_context import estimate_request_tokens
from app.runtime.turn_state import RuntimeTurnState
from app.services.system_llm_role_service import SystemLLMRoleService
from app.services.runtime_limits_service import RuntimeLimitsService
from app.services.system_role_prompt import compile_system_role_prompt

logger = get_logger(__name__)

# Last-resort prompt used only if the DB role cannot be loaded (schema drift,
# migration not run, etc.). Admins should edit the SYNTHESIZER row in
# `system_llm_roles` rather than this constant.
_FALLBACK_SYSTEM_PROMPT = (
    "Ты — редактор финального ответа корпоративного AI-портала. "
    "Ответь на вопрос и в направлении, заданных synthesis brief, используя "
    "источники текущего SYNTHESIS INPUT MODE. Не добавляй новые факты."
)
_FILE_DELIVERY_RULE = (
    "Сгенерированные файлы доставляются интерфейсом отдельными вложениями. "
    "Не добавляй в текст markdown-ссылки, URL или списки файлов; при необходимости "
    "можно кратко упомянуть имя готового файла. Никогда не придумывай имя, формат "
    "или содержимое файла: используй только имена из поля artifacts synthesis context. "
    "Если artifacts пуст, не утверждай, что файл создан или будет прикреплён."
)
_PLANNED_SYNTHESIS_MODE = (
    "# SYNTHESIS INPUT MODE\n"
    "mode=planned. Источником фактического содержания являются run_context.evidence, memory_context, completed_task_reports, "
    "результаты и пояснения всех задач с их статусами, runtime sources/artifacts и limitations. Не выдавай неуспешную работу за выполненную. "
    "synthesis_brief и plan_outline задают цель и форму ответа, а не доказывают выполнение. "
    "Не используй намерения задач или непроверенные утверждения как выполненный результат. "
    "Если подтверждённых данных нет, сообщи, что они не получены; причину называй только из diagnostics/limitations. "
    "Не выводи из пустых отчётов отсутствие интеграции или прав. "
    "Не обещай последующее получение данных или выполнение задач."
)
_DIRECT_SYNTHESIS_MODE = (
    "# SYNTHESIS INPUT MODE\n"
    "mode=direct. Отсутствие completed_task_reports нормально. Источником содержания являются "
    "direct_answer_draft, run_context.evidence и memory_context; synthesis_brief задаёт форму и разрешённую генерацию. Не требуй план, отчёты задач "
    "или новые данные. Не утверждай, что факт, запись памяти или иное действие уже завершены, "
    "если это не подтверждено в direct_answer_draft."
)

def _compile_role_prompt(role_config: Dict[str, object], role_override: Optional[Dict[str, object]]) -> str:
    return compile_system_role_prompt(role_config, role_override, fallback=_FALLBACK_SYSTEM_PROMPT)


class Synthesizer:
    """Streams the final answer from accumulated memory."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self._input_builder = SynthesizerInputBuilder()
        self._llm_client = llm_client
        self._streaming_call = RoleStreamingCall(session=session, llm_client=llm_client)

    async def stream(
        self,
        *,
        runtime_state: RuntimeTurnState,
        run_id: UUID,
        synthesis_context: Dict[str, Any],
        model: Optional[str] = None,
        platform_config: Optional[Dict[str, object]] = None,
        sandbox_overrides: Optional[Dict[str, object]] = None,
        budget_registry: Optional[BudgetRegistry] = None,
        budget_resolver: Optional[BudgetResolver] = None,
        logging_level: Optional[str] = None,
        ctx=None,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        # Completion belongs to this invocation only. A resumed/reused turn
        # state must never make a failed synthesis look successful.
        runtime_state.final_answer = None
        runtime_state.final_error = None
        synthesis_run_id = str(uuid4())
        synthesis_status = "completed"

        from app.runtime.datastore_context import build_datastore, load_result_catalog
        reports = synthesis_context.get("completed_task_reports") or []
        catalog, catalog_status = await load_result_catalog(ctx=ctx, run_id=str(run_id))
        selected_refs = self._selected_result_references(reports, synthesis_context.get("run_context") or {})
        catalog_by_id = {str(item.get("result_id")): item for item in catalog if item.get("result_id")}
        available_refs = [item for item in selected_refs if item["result_id"] in catalog_by_id]
        unavailable_refs = [item for item in selected_refs if item["result_id"] not in catalog_by_id]
        prepared_pages, read_limitations = await self._prepare_result_evidence(
            references=available_refs, catalog_by_id=catalog_by_id, ctx=ctx, run_id=str(run_id),
        )
        synthesis_context = {
            **synthesis_context,
            "evidence_preparation": {
                "catalog_status": catalog_status,
                "selected_result_refs": selected_refs,
                "available_result_refs": [item["result_id"] for item in available_refs],
                "unavailable_result_refs": unavailable_refs,
                "result_pages": prepared_pages,
                "coverage": ("unavailable" if unavailable_refs and not available_refs else
                             "partial" if unavailable_refs or read_limitations else
                             "available" if selected_refs else "no_selected_result_refs"),
                "limitations": read_limitations,
            },
        }
        synthesis_limitations = list(synthesis_context.get("limitations") or [])
        if unavailable_refs:
            synthesis_limitations.append({
                "code": "selected_result_unavailable",
                "message": "A selected result reference is absent from the current authorized run catalog.",
                "result_refs": unavailable_refs,
            })
        if read_limitations:
            synthesis_limitations.extend(read_limitations)
        synthesis_context["limitations"] = synthesis_limitations
        files = [
            *[item.model_dump(mode="json") for item in runtime_state.attachment_contexts
              if item.ref.artifact_id not in runtime_state.deleted_artifact_ids],
            *(synthesis_context.get("artifacts") or []), *(synthesis_context.get("sources") or []),
        ]
        synthesis_context = {**synthesis_context, "datastore": build_datastore(
            files=[item for item in files if str((item.get("ref") or item).get("artifact_id") or "")
                   not in runtime_state.deleted_artifact_ids],
            results=catalog, task_ids={str(item["task_id"]) for item in reports if item.get("task_id")},
            result_ids={item["result_id"] for item in available_refs}, results_status=catalog_status,
        )}
        from app.runtime.synthesis_context import SynthesisContextBuilder
        synthesis_context = SynthesisContextBuilder()._compact_to_limit(synthesis_context)
        from app.runtime.prompt_projections import synthesis_for_prompt
        synthesis_context = synthesis_for_prompt(synthesis_context)

        # Load synthesizer role config early for context snapshot
        synth_role_cfg = await self._load_role_config()
        role_override = ((sandbox_overrides or {}).get("role_overrides") or {}).get("synthesizer")
        brief = synthesis_context.get("synthesis_brief") or {}
        file_delivery = brief.get("delivery") in {"files", "text_and_files"} or bool(brief.get("files"))
        if file_delivery:
            from app.runtime.synthesis_files import FILE_OUTPUT_REQUIREMENTS
            # Text examples demonstrate a different transport contract. Do not
            # carry them (including sandbox examples) into file generation.
            role_override = {**(role_override or {}), "output_requirements": FILE_OUTPUT_REQUIREMENTS, "examples": []}
        if isinstance(role_override, dict):
            if role_override.get("model"):
                synth_role_cfg["model"] = str(role_override["model"])
            if role_override.get("temperature") is not None:
                synth_role_cfg["temperature"] = float(role_override["temperature"])
        synth_prompt = _compile_role_prompt(synth_role_cfg, role_override if isinstance(role_override, dict) else None)
        if synthesis_context.get("direct_answer_draft"):
            synth_prompt += f"\n\n{_DIRECT_SYNTHESIS_MODE}"
        else:
            synth_prompt += f"\n\n{_PLANNED_SYNTHESIS_MODE}"
        synth_prompt = f"{synth_prompt}\n\n# FILE DELIVERY\n{_FILE_DELIVERY_RULE}"
        synth_prompt += (
            "\n# RUN CONTEXT\nUse run_context.original_request, constraints and answer_requirements to preserve the user's intent. "
            "run_context.evidence contains observed source material; respect source identity, scope and truncation. "
            "evidence_preparation reports only deterministic result-reference availability and page coverage, not semantic sufficiency. "
            "If it is partial or unavailable, do not treat missing rows/material as proof of absence; state the limitation. "
            "run_context.conversation_materials contains only explicitly selected historical messages as task material. "
            "Use them for requested rewriting or comparison, never as proof of a current check or completed action. "
            "Full dialogue and the chat snapshot belong to preflight and are not part of this input. "
            "For content_mode=generative or mixed you may create requested examples and prose; do not invent company facts or claim unobserved actions. "
            "Selected run evidence may support the answer even when task reports are empty."
        )
        if (synthesis_context.get("execution_summary") or {}).get("partial"):
            synth_prompt += (
                "\n\n# PARTIAL ANSWER\n"
                "execution_summary.partial=true. Используй подтверждённую часть данных и ограничения из limitations."
            )
        synth_prompt += (
            "\n\n# MEMORY SCOPE GROUPS\n"
            "memory_context может содержать groups — независимые наборы поиска по scope. "
            "Сохраняй принадлежность утверждений к scope; ошибка группы не означает отсутствия сведений. "
            "Не приписывай свойства объекта из одного scope объекту другого scope. "
            "\n\n# EXECUTION FOCUS\n"
            "scope_context — подтверждённый приложением текущий набор scope чата. "
            "Используй его для понимания области ответа. Он не доказывает внешние результаты. "
            "Пустой фокус допустим; не задавай вопрос о техническом скоупе и не требуй выбрать его для готового ответа."
        )

        if budget_registry is not None:
            synthesis_limits = None
            if budget_resolver is not None:
                try:
                    synthesis_limits = await budget_resolver.resolve_orchestrator("synthesizer", sandbox_overrides)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to resolve synthesizer limits: %s", exc)
            budget_registry.register(
                entity_type="synthesis_run",
                entity_id=synthesis_run_id,
                parent_entity_id=str(run_id),
                role="synthesizer",
                limits=synthesis_limits,
            )
            init_payload = budget_registry.emit_snapshot(synthesis_run_id, reason="init") or {}
            yield RuntimeEvent.budget_snapshot(
                entity_type="synthesis_run",
                entity_id=synthesis_run_id,
                parent_entity_type="run",
                parent_entity_id=str(run_id),
                role="synthesizer",
                own=init_payload.get("own", {}),
                limits=init_payload.get("limits"),
                delta={},
                reason="init",
                at_ms=init_payload.get("at_ms"),
            )
        else:
            synthesis_limits = None
        yield RuntimeEvent.synthesis_start(
            synthesis_id=synthesis_run_id,
            run_id=str(run_id),
            context_snapshot=compact_snapshot(
                inputs={
                    "synthesis_brief": synthesis_context.get("synthesis_brief", {}),
                    "completed_task_count": len(synthesis_context.get("completed_task_reports", [])),
                },
                prompt=prompt_snapshot(synth_prompt, logging_level),
                limits=serialize_limits(synthesis_limits),
                meta={
                    "role": "synthesizer",
                    "model": synth_role_cfg.get("model") or model,
                },
            ),
        )
        yield RuntimeEvent.status(
            "memory_context_used",
            entity_type="synthesis_run", entity_id=synthesis_run_id,
            parent_entity_type="run", parent_entity_id=str(run_id),
            memory_context=synthesis_context.get("memory_context") or [],
        )
        sources = list(synthesis_context.get("sources") or [])
        attachments = self._attachments_from_context(synthesis_context)

        if ctx is not None and attachments:
            from app.services.chat_artifact_reference_service import ChatArtifactReferenceService
            requested = [item["artifact_id"] for item in attachments]
            resolved = await ChatArtifactReferenceService(self.session).resolve_many(
                artifact_ids=requested, chat_id=str(ctx.chat_id), owner_id=str(ctx.user_id), tenant_id=str(ctx.tenant_id))
            if set(requested) != set(resolved):
                raise ValueError("Selected answer artifacts are unavailable")
        brief = synthesis_context.get("synthesis_brief") or {}
        if brief.get("delivery") in {"files", "text_and_files"} or brief.get("files"):
            from app.runtime.synthesis_files import generate_file_answer
            file_events = []
            try:
                file_prompt = synth_prompt.replace(_FILE_DELIVERY_RULE, "Create requested files using the structured file response contract.")
                full, created, file_events = await generate_file_answer(
                    session=self.session, llm_client=self._llm_client, state=runtime_state,
                    context=synthesis_context, prompt=file_prompt, ctx=ctx, synthesis_id=synthesis_run_id,
                    sandbox_overrides={**(sandbox_overrides or {}), "role_overrides": {
                        **((sandbox_overrides or {}).get("role_overrides") or {}),
                        "synthesizer": {**(((sandbox_overrides or {}).get("role_overrides") or {}).get("synthesizer") or {}),
                                        **({"model": model} if model else {})}}}, budget_registry=budget_registry, events=file_events)
                for event in file_events:
                    yield event
                attachments.extend(created)
                runtime_state.run_context.delivered_artifacts = attachments
                runtime_state.final_answer = full
                yield RuntimeEvent.final_answer_marker(
                    synthesis_id=synthesis_run_id,
                    run_id=str(run_id),
                    content=full,
                    sources=sources,
                    attachments=attachments,
                    producer="synthesizer_file_generation",
                )
                yield RuntimeEvent.final(full, sources=sources, run_id=str(run_id), attachments=attachments,
                    entity_type="synthesis_run", entity_id=synthesis_run_id,
                    parent_entity_type="run", parent_entity_id=str(run_id))
                yield RuntimeEvent.synthesis_end(synthesis_id=synthesis_run_id, run_id=str(run_id), status="completed")
            except Exception:
                for event in file_events:
                    yield event
                logger.exception("synthesis_file_generation_failed", extra={"run_id": str(run_id)})
                runtime_state.final_error = "Не удалось подготовить файл ответа. Повторите запрос."
                yield RuntimeEvent.error(runtime_state.final_error, recoverable=True,
                    error_code="synthesis_file_failed", user_message=runtime_state.final_error,
                    parent_entity_type="synthesis_run", parent_entity_id=synthesis_run_id)
                yield RuntimeEvent.synthesis_end(synthesis_id=synthesis_run_id, run_id=str(run_id), status="failed")
            return

        # Full synthesis path. Role configuration owns prompt, model and
        # temperature. Call limits and transport parameters belong to the
        # selected model deployment.
        # caller-supplied `model` still wins when provided.
        role_cfg = synth_role_cfg
        system_prompt = synth_prompt
        effective_model = model or role_cfg.get("model")
        params: Dict[str, float] = {}
        if role_cfg.get("temperature") is not None:
            params["temperature"] = role_cfg["temperature"]

        yield RuntimeEvent.status(
            "synthesizing", entity_type="synthesis_run", entity_id=synthesis_run_id,
            parent_entity_type="run", parent_entity_id=str(run_id),
        )
        messages = self._input_builder.build(
            synthesis_context=synthesis_context,
            system_prompt=system_prompt,
        )
        full = ""
        try:
            model_call_config = await RuntimeLimitsService(self.session).resolve_model(effective_model)
            max_retries = model_call_config.max_retries
        except Exception as exc:  # noqa: BLE001
            # A role prompt can be served from a fallback even while the model
            # registry is temporarily unavailable. Keep the same safe default
            # used by RuntimeLimitsService in that degraded mode.
            logger.warning("Failed to resolve synthesizer model retry policy: %s", exc)
            max_retries = 2
        # One synthesis request may retry internally, but the frontend must
        # see one request/response entity until the final answer is produced.
        llm_call_id = str(uuid4())
        logical_llm_call_id = str(uuid4())
        for attempt in range(max_retries + 1):
            retry_scheduled = False
            emitted_delta = False
            # Emit before opening the stream so a provider timeout/error still has
            # a stable LLM child in the sandbox journal.
            yield RuntimeEvent.llm_request(
                llm_call_id=llm_call_id,
                logical_llm_call_id=logical_llm_call_id,
                model=effective_model or "unknown",
                messages=messages,
                parent_entity_type="synthesis_run",
                parent_entity_id=synthesis_run_id,
                purpose="final_answer",
                actor_type="synthesizer",
                actor_entity_id=synthesis_run_id,
                input_tokens_estimate=estimate_request_tokens({"model": effective_model, "messages": messages, **(params or {})}),
            )
            async for stream_event in self._streaming_call.invoke_stream(
                role=SystemLLMRoleType.SYNTHESIZER,
                messages=messages,
                llm_call_id=llm_call_id,
                role_config=role_cfg,
                model_override=effective_model,
                params_override=params or None,
                sandbox_overrides=sandbox_overrides,
                budget_registry=budget_registry,
                budget_entity_id=synthesis_run_id,
            ):
                if isinstance(stream_event, StreamContext):
                    yield RuntimeEvent.status("llm_context_allocated", entity_type="llm_call", entity_id=llm_call_id,
                        parent_entity_type="synthesis_run", parent_entity_id=synthesis_run_id,
                        attempt=attempt + 1, **stream_event.allocation)
                    continue
                if isinstance(stream_event, StreamDelta):
                    if stream_event.chunk:
                        emitted_delta = True
                        yield RuntimeEvent.delta(stream_event.chunk)
                    continue
                if isinstance(stream_event, StreamError):
                    may_retry = stream_event.recoverable and attempt < max_retries and not emitted_delta
                    yield RuntimeEvent.llm_response(
                        llm_call_id=llm_call_id,
                        logical_llm_call_id=logical_llm_call_id,
                        model=effective_model or "unknown",
                        error_type=stream_event.error_type,
                        error_code=stream_event.code,
                        retryable=may_retry,
                        status=("waiting_retry" if may_retry else "failed"),
                        terminal=not may_retry,
                        attempt=attempt + 1,
                        max_attempts=max_retries + 1,
                        retry_after_ms=stream_event.retry_after_ms,
                        **(stream_event.provider_diagnostics or {}),
                        parent_entity_type="synthesis_run",
                        parent_entity_id=synthesis_run_id,
                        purpose="final_answer",
                        actor_type="synthesizer",
                        actor_entity_id=synthesis_run_id,
                    )
                    if may_retry:
                        retry_delay_ms = self._retry_delay_ms(
                            attempt=attempt,
                            retry_after_ms=stream_event.retry_after_ms,
                            strategy="exp",
                        )
                        yield RuntimeEvent(
                            RuntimeEventType.PROTOCOL_RETRY,
                            {
                                "reason": "transport_error",
                                "attempt": attempt + 1,
                                "max_attempts": max_retries + 1,
                                "retry_delay_ms": retry_delay_ms,
                                "retry_after_ms": stream_event.retry_after_ms,
                                "llm_call_id": llm_call_id,
                                "logical_llm_call_id": logical_llm_call_id,
                                "entity_type": "llm_call",
                                "entity_id": llm_call_id,
                                "parent_entity_type": "synthesis_run",
                                "parent_entity_id": synthesis_run_id,
                            },
                        )
                        await asyncio.sleep(retry_delay_ms / 1000)
                        retry_scheduled = True
                        break
                    synthesis_status = "failed"
                    yield RuntimeEvent.error(
                        stream_event.message,
                        recoverable=stream_event.recoverable,
                        error_code=stream_event.code,
                        user_message=stream_event.message,
                        operator_message=stream_event.operator_message or stream_event.message,
                        source="llm",
                        error_type=stream_event.error_type,
                        debug=stream_event.debug,
                        **(stream_event.provider_diagnostics or {}),
                        parent_entity_type="synthesis_run",
                        parent_entity_id=synthesis_run_id,
                    )
                    runtime_state.final_error = stream_event.message
                    yield RuntimeEvent.synthesis_end(
                        synthesis_id=synthesis_run_id,
                        run_id=str(run_id),
                        status=synthesis_status,
                    )
                    return
                if isinstance(stream_event, StreamTurn):
                    if stream_event.partial:
                        synthesis_status = "failed"
                        runtime_state.final_error = "synthesizer_partial_response"
                        yield RuntimeEvent.llm_response(
                            llm_call_id=stream_event.llm_call_id,
                            logical_llm_call_id=logical_llm_call_id,
                            model=effective_model or stream_event.model or "unknown",
                            content=stream_event.content,
                            response_length=stream_event.response_length,
                            tokens_in=stream_event.tokens_in,
                            tokens_out=stream_event.tokens_out,
                            tokens_total=stream_event.tokens_total,
                            token_source="estimate",
                            duration_ms=stream_event.duration_ms,
                            error_code="synthesizer_partial_response",
                            safe_message="The synthesis stream ended before completion.",
                            **(stream_event.provider_diagnostics or {}),
                            retryable=False,
                            status="failed",
                            terminal=True,
                            attempt=attempt + 1,
                            max_attempts=max_retries + 1,
                            parent_entity_type="synthesis_run",
                            parent_entity_id=synthesis_run_id,
                            purpose="final_answer",
                            actor_type="synthesizer",
                            actor_entity_id=synthesis_run_id,
                        )
                        yield RuntimeEvent.error(
                            "Не удалось завершить итоговый ответ.",
                            recoverable=False,
                            error_code="synthesizer_partial_response",
                            user_message="Не удалось завершить итоговый ответ.",
                            operator_message=stream_event.error_message or "Synthesis stream ended after partial output",
                            **(stream_event.provider_diagnostics or {}),
                            source="llm",
                            parent_entity_type="synthesis_run",
                            parent_entity_id=synthesis_run_id,
                        )
                        yield RuntimeEvent.synthesis_end(
                            synthesis_id=synthesis_run_id,
                            run_id=str(run_id),
                            status=synthesis_status,
                        )
                        return
                    full = (stream_event.content or "").strip()
                    if budget_registry is not None:
                        delta_payload: Dict[str, int] = {}
                        if stream_event.tokens_in > 0:
                            delta_payload["tokens_in"] = stream_event.tokens_in
                        if stream_event.tokens_out > 0:
                            delta_payload["tokens_out"] = stream_event.tokens_out
                        if stream_event.tokens_total > 0:
                            delta_payload["tokens_total"] = stream_event.tokens_total
                        if stream_event.duration_ms > 0:
                            delta_payload["wall_time_ms"] = stream_event.duration_ms
                        if delta_payload:
                            snap = budget_registry.emit_snapshot(
                                synthesis_run_id,
                                reason="llm_turn",
                                delta=delta_payload,
                            ) or {}
                            yield RuntimeEvent.budget_snapshot(
                                entity_type="synthesis_run",
                                entity_id=synthesis_run_id,
                                parent_entity_type="run",
                                parent_entity_id=str(run_id),
                                role="synthesizer",
                                own=snap.get("own", {}),
                                limits=snap.get("limits"),
                                delta=delta_payload,
                                reason="llm_turn",
                                at_ms=snap.get("at_ms"),
                            )
                    yield RuntimeEvent.llm_response(
                        llm_call_id=stream_event.llm_call_id,
                        logical_llm_call_id=logical_llm_call_id,
                        model=effective_model or stream_event.model or "unknown",
                        content=full, response_length=stream_event.response_length,
                        tokens_in=stream_event.tokens_in, tokens_out=stream_event.tokens_out,
                        tokens_total=stream_event.tokens_total, token_source="estimate",
                        duration_ms=stream_event.duration_ms,
                        result_kind="answer", status="completed", terminal=True,
                        attempt=attempt + 1, max_attempts=max_retries + 1,
                        parent_entity_type="synthesis_run", parent_entity_id=synthesis_run_id,
                        purpose="final_answer", actor_type="synthesizer", actor_entity_id=synthesis_run_id,
                    )
            if retry_scheduled:
                continue
            break
        if not full:
            synthesis_status = "failed"
            runtime_state.final_error = "synthesizer_empty_response"
            yield RuntimeEvent.error(
                "Не удалось сформировать итоговый ответ.",
                recoverable=False,
                error_code="synthesizer_empty_response",
                user_message="Не удалось сформировать итоговый ответ.",
                operator_message="Synthesizer returned an empty final answer",
                source="runtime",
                parent_entity_type="synthesis_run",
                parent_entity_id=synthesis_run_id,
            )
            yield RuntimeEvent.synthesis_end(
                synthesis_id=synthesis_run_id,
                run_id=str(run_id),
                status=synthesis_status,
            )
            return

        runtime_state.final_answer = full
        yield RuntimeEvent.final_answer_marker(
            synthesis_id=synthesis_run_id,
            run_id=str(run_id),
            content=full,
            sources=sources,
            attachments=attachments,
            producer="synthesizer_llm",
        )
        runtime_state.run_context.delivered_artifacts = attachments
        yield RuntimeEvent.final(
            full, sources=sources, run_id=str(run_id), attachments=attachments,
            entity_type="synthesis_run", entity_id=synthesis_run_id,
            parent_entity_type="run", parent_entity_id=str(run_id),
        )
        if budget_registry is not None:
            final_payload = budget_registry.emit_snapshot(synthesis_run_id, reason="finalize") or {}
            yield RuntimeEvent.budget_snapshot(
                entity_type="synthesis_run",
                entity_id=synthesis_run_id,
                parent_entity_type="run",
                parent_entity_id=str(run_id),
                role="synthesizer",
                own=final_payload.get("own", {}),
                limits=final_payload.get("limits"),
                delta={},
                reason="finalize",
                at_ms=final_payload.get("at_ms"),
            )
        yield RuntimeEvent.synthesis_end(
            synthesis_id=synthesis_run_id,
            run_id=str(run_id),
            status=synthesis_status,
        )

    # ---------------------------------------------------------------- helpers --

    @staticmethod
    def _selected_result_references(
        reports: List[Dict[str, Any]], run_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Select only explicit successful receipts and selected result-tool evidence."""
        allowed_tools = {"result.read", "result.describe", "result.sql", "result.analyze",
                         "result.aggregate", "result.find", "result.load"}
        selected: Dict[tuple[Any, ...], Dict[str, Any]] = {}

        def view_key(item: Dict[str, Any]) -> tuple[Any, ...]:
            # Serialized ResultObservation keeps unknown fields as explicit null.
            fields = tuple(field for field in (item.get("fields") or []) if isinstance(field, str))
            return (str(item.get("result_id") or ""), item.get("revision"), item.get("offset"),
                    fields, item.get("path"), item.get("text_offset"), item.get("text_limit"),
                    item.get("next_text_offset"), item.get("child_offset"), item.get("child_limit"),
                    item.get("next_child_offset"), item.get("view"))

        def add(item: Dict[str, Any]) -> None:
            result_id = str(item.get("result_id") or "")
            if not result_id:
                return
            observation = item.get("observation") if isinstance(item.get("observation"), dict) else {}
            reader_arguments = item.get("reader_arguments") if isinstance(item.get("reader_arguments"), dict) else {}
            # The runtime observation is authoritative for what was actually
            # returned. The original read arguments fill any request-only
            # fields that the receipt does not repeat.
            for name in ("offset", "limit", "fields", "path", "text_offset", "text_limit",
                         "child_offset", "child_limit", "view"):
                if name in observation:
                    item[name] = observation[name]
                elif name not in item and name in reader_arguments:
                    item[name] = reader_arguments[name]
            if not reader_arguments:
                item.pop("reader_arguments", None)
            key = view_key(item)
            previous = selected.get(key)
            previous_revision = previous.get("revision") if previous else None
            revision = item.get("revision")
            other_revisions = {
                int(existing["revision"]) for existing in selected.values()
                if existing.get("result_id") == result_id and isinstance(existing.get("revision"), int)
            }
            if revision is not None and any(existing_revision != int(revision) for existing_revision in other_revisions):
                conflict = sorted({*other_revisions, int(revision)})
                item["revision_conflict"] = conflict
                for existing in selected.values():
                    if existing.get("result_id") == result_id:
                        existing["revision_conflict"] = conflict
            if previous and revision is not None and previous_revision is not None and revision != previous_revision:
                previous["revision_conflict"] = sorted({int(previous_revision), int(revision)})
            elif previous is None or (previous_revision is None and revision is not None):
                selected[key] = item

        for report in reports:
            for reference in report.get("verified_result_refs") or []:
                if not isinstance(reference, dict) or not reference.get("result_id"):
                    continue
                item = {key: reference[key] for key in (
                    "result_id", "operation", "revision", "source_complete", "source_total", "row_count",
                    "observation", "reader_arguments", "offset", "limit", "fields", "path",
                    "text_offset", "text_limit", "child_offset", "child_limit", "view") if key in reference}
                add(item)
        for evidence in run_context.get("evidence") or []:
            if not isinstance(evidence, dict) or evidence.get("tool") not in allowed_tools:
                continue
            data = evidence.get("data") if isinstance(evidence.get("data"), dict) else {}
            result_id = data.get("result_id")
            if not isinstance(result_id, str) or not result_id:
                continue
            arguments = evidence.get("arguments") if isinstance(evidence.get("arguments"), dict) else {}
            add({
                "result_id": result_id, "operation": str(evidence["tool"]),
                **({"revision": data["revision"]} if isinstance(data.get("revision"), int) else {}),
                **({"source_complete": data["source_complete"]} if isinstance(data.get("source_complete"), bool) else {}),
                **({"offset": arguments["offset"]} if isinstance(arguments.get("offset"), int) else {}),
                **({"limit": arguments["limit"]} if isinstance(arguments.get("limit"), int) else {}),
                **({"fields": arguments["fields"]} if isinstance(arguments.get("fields"), list) else {}),
                **({"path": arguments["path"]} if isinstance(arguments.get("path"), str) else {}),
                **({key: arguments[key] for key in ("text_offset", "text_limit", "child_offset", "child_limit", "view")
                   if key in arguments}),
                "reader_arguments": dict(arguments),
                **({"observation": data["result_observation"]}
                   if isinstance(data.get("result_observation"), dict) else {}),
            })
        return sorted(selected.values(), key=lambda item: tuple(str(value or "") for value in view_key(item)))

    @staticmethod
    async def _prepare_result_evidence(
        *, references: List[Dict[str, Any]], catalog_by_id: Dict[str, Dict[str, Any]],
        ctx: Any, run_id: str,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Read one bounded page from already stored, current-user authorized datasets."""
        if not references:
            return [], []
        if ctx is None or not getattr(ctx, "user_id", None) or not getattr(ctx, "tenant_id", None):
            return [], [{"code": "selected_result_read_unavailable",
                         "message": "Selected saved results could not be resolved without the current user scope."}]
        from app.core.config import get_settings
        from app.services.result_workspace import ResultWorkspace

        settings = get_settings()
        per_result_budget = max(256, int(settings.TOOL_RESULTS_CONTEXT_TOKENS) // len(references))
        workspace = ResultWorkspace()
        pages: List[Dict[str, Any]] = []
        limitations: List[Dict[str, Any]] = []
        for reference in references:
            result_id = str(reference["result_id"])
            if reference.get("revision_conflict"):
                limitations.append({
                    "code": "selected_result_revision_conflict",
                    "message": "Selected evidence refers to different revisions of the same saved result; no page was read.",
                    "result_id": result_id, "revisions": reference["revision_conflict"],
                })
                continue
            catalog_entry = catalog_by_id[result_id]
            current_revision = int(catalog_entry.get("revision") or 1)
            expected_revision = reference.get("revision")
            if expected_revision is None:
                limitations.append({
                    "code": "selected_result_revision_unpinned",
                    "message": "A selected result has no observed revision; synthesis did not read a potentially changed snapshot.",
                    "result_id": result_id, "current_revision": current_revision,
                })
                continue
            if int(expected_revision) != current_revision:
                limitations.append({
                    "code": "selected_result_revision_changed",
                    "message": "A selected result changed revision before synthesis; its page was not read.",
                    "result_id": result_id, "expected_revision": expected_revision,
                    "current_revision": current_revision,
                })
                continue
            try:
                offset = reference.get("offset", 0)
                limit = min(5, max(1, int(reference.get("limit") or 5)))
                fields = reference.get("fields")
                reader_arguments = reference.get("reader_arguments") if isinstance(reference.get("reader_arguments"), dict) else {}
                read_kwargs: Dict[str, Any] = {}
                for key in ("path", "text_offset", "text_limit", "child_offset", "child_limit", "view"):
                    value = reference.get(key, reader_arguments.get(key))
                    if value is not None:
                        read_kwargs[key] = value
                if read_kwargs.get("path") is not None:
                    limit = 1
                page = await workspace.read(
                    result_id=result_id, run_id=run_id, tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                    offset=offset if isinstance(offset, int) and offset >= 0 else 0,
                    limit=limit, fields=fields if isinstance(fields, list) else None, revision=current_revision,
                    **read_kwargs,
                    context_budget_tokens=per_result_budget,
                    context_model=None,
                )
            except Exception:
                logger.warning("Selected result could not be read for synthesis result_id=%s", result_id, exc_info=True)
                limitations.append({
                    "code": "selected_result_read_unavailable",
                    "message": "A selected saved result could not be read under the current access scope.",
                    "result_id": result_id,
                })
                continue
            pages.append({
                "result_id": result_id, "revision": page["revision"],
                "records": page.get("value", []),
                "read_complete": bool(page.get("read_complete")),
                "next_offset": page.get("next_offset"),
                "record_too_large": bool(page.get("record_too_large")),
                "source_complete": page.get("source_complete"),
                "source_total": catalog_entry.get("source_total"),
                "stored_count": catalog_entry.get("row_count", 0),
                "offset": page.get("offset", offset), "limit": page.get("limit", limit),
                "path": page.get("path"), "view": page.get("view"),
                "text_offset": page.get("text_offset"), "text_limit": page.get("text_limit"),
                "next_text_offset": page.get("next_text_offset"),
                "child_offset": page.get("child_offset"), "child_limit": page.get("child_limit"),
                "next_child_offset": page.get("next_child_offset"),
                **({"requested_fields": page["requested_fields"]} if "requested_fields" in page else {}),
            })
            if (page.get("record_too_large") or page.get("next_offset") is not None
                    or page.get("next_text_offset") is not None or page.get("next_child_offset") is not None):
                limitations.append({
                    "code": "selected_result_page_partial",
                    "message": "Only the observed bounded saved-data view is included in synthesis evidence.",
                    "result_id": result_id, "next_offset": page.get("next_offset"),
                    "next_text_offset": page.get("next_text_offset"),
                    "next_child_offset": page.get("next_child_offset"),
                    "path": page.get("path"), "view": page.get("view"),
                    "record_too_large": bool(page.get("record_too_large")),
                })
        return pages, limitations

    @staticmethod
    def _attachments_from_context(
        synthesis_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Create delivery references only from verified synthesis artifacts."""
        result: List[Dict[str, Any]] = []
        seen_artifact_ids: set[str] = set()
        for att in synthesis_context.get("artifacts") or []:
            artifact_id = str(att.get("artifact_id") or "").strip() if isinstance(att, dict) else ""
            if not artifact_id or artifact_id in seen_artifact_ids:
                continue
            seen_artifact_ids.add(artifact_id)
            result.append({
                "artifact_id": artifact_id,
                "file_name": att.get("file_name") or att.get("name") or "file",
                "download_url": f"/api/v1/files/{artifact_id}/download",
                "content_type": att.get("content_type") or "",
                "size_bytes": att.get("size_bytes"),
                **({"artifact": att["artifact"]} if isinstance(att.get("artifact"), dict) else {}),
            })
        return result

    async def _load_role_config(self) -> Dict[str, object]:
        """Load SYNTHESIZER role config from DB with a safe fallback."""
        try:
            service = SystemLLMRoleService(self.session)
            return await service.get_role_config(SystemLLMRoleType.SYNTHESIZER)
        except Exception as exc:
            logger.warning(
                "Synthesizer role config load failed, falling back to defaults: %s",
                exc,
            )
            return {
                "prompt": _FALLBACK_SYSTEM_PROMPT,
                "model": None,
                "temperature": 0.3,
            }


    @staticmethod
    def _retry_delay_ms(
        *,
        attempt: int,
        retry_after_ms: Optional[int],
        strategy: str = "exp",
    ) -> int:
        """Bound retry delay and respect a provider supplied cooldown."""
        if strategy == "none":
            base_ms = 0
        elif strategy == "linear":
            base_ms = min(10_000, 500 * (attempt + 1))
        else:
            base_ms = min(10_000, 500 * (2 ** max(0, attempt)))
        if retry_after_ms is None:
            return base_ms
        return max(base_ms, max(0, retry_after_ms))
