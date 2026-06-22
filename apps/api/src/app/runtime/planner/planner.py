"""
Planner — decides the next step of the run.

Key properties:
    * Planner talks only to **agents**, never to operations/tools directly.
    * Stateless: each call reads RuntimeTurnState and produces one NextStep.
    * Output is strictly validated; invalid decisions trigger a single retry
      with an explicit error message prepended to the payload.

The seed prompt (see app.runtime.seeds.system_roles) enforces the schema below
in `output_requirements`. The model field names in the prompt must match.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.contracts import ExecutionMode, NextStep, NextStepKind
from app.runtime.input_builders import PlannerInputBuilder
from app.runtime.llm.structured import StructuredLLMCall, StructuredCallError
from app.runtime.planner.validator import validate_next_step
from app.runtime.turn_state import RuntimeTurnState

logger = get_logger(__name__)


@dataclass
class PlannerLLMTrace:
    attempt: int
    success: bool
    llm_call_id: str
    model: str
    request_messages: list[dict[str, Any]]
    raw_response: str
    response_length: int
    duration_ms: int
    retry_reason: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_total: int = 0
    step_kind: str = "decision"
    structured_input: Dict[str, Any] = field(default_factory=dict)
    parsed_response: Dict[str, Any] = field(default_factory=dict)


class ThinkingHypothesis(BaseModel):
    summary: str = Field(..., min_length=1)
    expected_outcome: str = Field(..., min_length=1)
    risks: List[str] = Field(default_factory=list)
    fit: str = Field(..., min_length=1)


class PlannerThinkingOutput(BaseModel):
    hypotheses: List[ThinkingHypothesis] = Field(..., min_length=2, max_length=3)
    selected_hypothesis_index: int = Field(..., ge=0, le=2)
    selected_action_kind: Literal[
        "call_agent",
        "clarify",
        "ask_user",
        "final",
        "abort",
    ]
    selected_action_summary: str = Field(..., min_length=1)
    selection_rationale: str = Field(..., min_length=1)

    @field_validator("selected_hypothesis_index")
    @classmethod
    def _validate_selected_index(cls, value: int, info) -> int:
        hypotheses = info.data.get("hypotheses") if hasattr(info, "data") else None
        if isinstance(hypotheses, list) and value >= len(hypotheses):
            raise ValueError("selected_hypothesis_index must point to an existing hypothesis")
        return value


class PlannerLLMOutput(BaseModel):
    """Schema the planner LLM is required to produce."""

    kind: Literal[
        "call_agent",
        "clarify",
        "ask_user",
        "final",
        "abort",
    ]
    rationale: str = Field(..., min_length=1)
    agent_slug: Optional[str] = None
    agent_input: Dict[str, Any] = Field(default_factory=dict)
    question: Optional[str] = None
    final_answer: Optional[str] = None
    phase_id: Optional[str] = None
    phase_title: Optional[str] = None
    risk: Literal["low", "medium", "high"] = "low"
    requires_confirmation: bool = False

    @field_validator("agent_input", mode="before")
    @classmethod
    def _coerce_agent_input(cls, value: Any) -> Dict[str, Any]:
        """Be tolerant to planner outputs that stringify JSON objects.

        Example from logs:
            "agent_input": "{\"query\":\"...\"}"
        """
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {"query": text}
            if isinstance(parsed, dict):
                return parsed
            return {"query": text}
        # Defensive fallback for unexpected structured values.
        return {"query": str(value)}


class Planner:
    """One-LLM-call next-step planner."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.llm = StructuredLLMCall(session=session, llm_client=llm_client)
        self._input_builder = PlannerInputBuilder()

    async def next_step(
        self,
        *,
        runtime_state: RuntimeTurnState,
        available_agents: List[Dict[str, Any]],
        outline: Optional[Dict[str, Any]] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        agent_run_id: Optional[UUID] = None,
        planner_iteration_id: Optional[str] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> tuple[NextStep, List[PlannerLLMTrace]]:
        allowed_slugs = [a.get("slug") for a in available_agents if a.get("slug")]
        payload_base = self._input_builder.build(
            runtime_state=runtime_state,
            available_agents=available_agents,
            outline=outline,
            platform_config=platform_config,
        )
        execution_mode = getattr(runtime_state, "execution_mode", ExecutionMode.NORMAL)

        # First attempt — normal payload. On structural or validator failure, retry
        # once with an explicit error appended so the model can correct itself.
        last_error: Optional[str] = None
        traces: List[PlannerLLMTrace] = []
        if execution_mode == ExecutionMode.THINKING:
            thinking_trace = await self._deliberate_next_action(
                payload_base=payload_base,
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_run_id=agent_run_id,
                planner_iteration_id=planner_iteration_id,
                sandbox_overrides=sandbox_overrides,
            )
            traces.append(thinking_trace)
            if thinking_trace.success and thinking_trace.parsed_response:
                payload_base["planner_thinking"] = thinking_trace.parsed_response
                payload_base["execution_mode"] = ExecutionMode.THINKING.value
        for attempt in range(2):
            payload = dict(payload_base)
            if last_error:
                payload["previous_error"] = last_error

            llm_call_id = (
                f"{planner_iteration_id}:planner-llm:{attempt + 1}"
                if planner_iteration_id
                else f"planner-llm:{attempt + 1}"
            )
            try:
                result = await self.llm.invoke(
                    role=SystemLLMRoleType.PLANNER,
                    # system_prompt left unset → StructuredLLMCall loads the
                    # compiled prompt from the active PLANNER system_llm_roles row.
                    payload=payload,
                    schema=PlannerLLMOutput,
                    chat_id=chat_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_run_id=agent_run_id,
                    sandbox_overrides=sandbox_overrides,
                )
            except StructuredCallError as exc:
                last_error = f"schema_error: {exc}"
                raw_response = str(exc)
                traces.append(
                    PlannerLLMTrace(
                        attempt=attempt + 1,
                        success=False,
                        llm_call_id=llm_call_id,
                        model="unknown",
                        request_messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
                        raw_response=raw_response,
                        response_length=len(raw_response),
                        duration_ms=0,
                        retry_reason=last_error,
                        tokens_in=0,
                        tokens_out=0,
                        tokens_total=0,
                        step_kind="decision",
                        structured_input=payload,
                    )
                )
                continue

            candidate = self._to_next_step(result.value)
            request_text = json.dumps(payload, ensure_ascii=False, default=str)
            current_trace = PlannerLLMTrace(
                attempt=attempt + 1,
                success=False,
                llm_call_id=llm_call_id,
                model=result.model or "unknown",
                request_messages=result.request_messages,
                raw_response=result.raw_response,
                response_length=len(result.raw_response or ""),
                duration_ms=result.duration_ms,
                tokens_in=self._estimate_tokens(request_text),
                tokens_out=self._estimate_tokens(result.raw_response or ""),
                tokens_total=(
                    self._estimate_tokens(request_text)
                    + self._estimate_tokens(result.raw_response or "")
                ),
                step_kind="decision",
                structured_input=payload,
                parsed_response=result.value.model_dump(mode="json"),
            )

            err = validate_next_step(
                candidate,
                allowed_agents=allowed_slugs,
                runtime_state=runtime_state,
            )
            if err is None:
                current_trace.success = True
                traces.append(current_trace)
                return candidate, traces

            logger.info("Planner validation retry (attempt=%s): %s", attempt, err)
            last_error = err
            current_trace.retry_reason = err
            traces.append(current_trace)

        # Two attempts failed → safe forced finalize if we have facts, else abort.
        return self._safe_fallback(runtime_state, last_error), traces

    async def _deliberate_next_action(
        self,
        *,
        payload_base: Dict[str, Any],
        chat_id: Optional[UUID],
        tenant_id: Optional[UUID],
        user_id: Optional[UUID],
        agent_run_id: Optional[UUID],
        planner_iteration_id: Optional[str],
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> PlannerLLMTrace:
        payload = {
            **payload_base,
            "execution_mode": ExecutionMode.THINKING.value,
            "thinking_instruction": {
                "task": "Generate 2-3 compact hypotheses for the next action only, select one, and explain the selection briefly.",
                "constraints": [
                    "Do not answer the user directly",
                    "Do not propose more than one chosen action",
                    "Keep summaries concise and operator-safe",
                ],
            },
        }
        llm_call_id = (
            f"{planner_iteration_id}:planner-thinking"
            if planner_iteration_id
            else "planner-thinking"
        )
        request_text = json.dumps(payload, ensure_ascii=False, default=str)
        try:
            result = await self.llm.invoke(
                role=SystemLLMRoleType.PLANNER,
                payload=payload,
                schema=PlannerThinkingOutput,
                system_prompt=self._thinking_system_prompt(),
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_run_id=agent_run_id,
                sandbox_overrides=sandbox_overrides,
            )
            parsed = self._thinking_summary_payload(result.value)
            return PlannerLLMTrace(
                attempt=1,
                success=True,
                llm_call_id=llm_call_id,
                model=result.model or "unknown",
                request_messages=result.request_messages,
                raw_response=result.raw_response,
                response_length=len(result.raw_response or ""),
                duration_ms=result.duration_ms,
                tokens_in=self._estimate_tokens(request_text),
                tokens_out=self._estimate_tokens(result.raw_response or ""),
                tokens_total=self._estimate_tokens(request_text) + self._estimate_tokens(result.raw_response or ""),
                step_kind="thinking",
                structured_input=payload,
                parsed_response=parsed,
            )
        except StructuredCallError as exc:
            raw_response = str(exc)
            return PlannerLLMTrace(
                attempt=1,
                success=False,
                llm_call_id=llm_call_id,
                model="unknown",
                request_messages=[{"role": "user", "content": request_text}],
                raw_response=raw_response,
                response_length=len(raw_response),
                duration_ms=0,
                retry_reason=f"thinking_schema_error: {exc}",
                tokens_in=self._estimate_tokens(request_text),
                tokens_out=0,
                tokens_total=self._estimate_tokens(request_text),
                step_kind="thinking",
                structured_input=payload,
            )

    # --------------------------------------------------------------- helpers --

    @staticmethod
    def _to_next_step(raw: PlannerLLMOutput) -> NextStep:
        kind_map = {
            "call_agent": NextStepKind.CALL_AGENT,
            "clarify": NextStepKind.CLARIFY,
            "ask_user": NextStepKind.ASK_USER,
            "final": NextStepKind.FINAL,
            "abort": NextStepKind.ABORT,
        }
        return NextStep(
            kind=kind_map[raw.kind],
            rationale=raw.rationale,
            agent_slug=raw.agent_slug,
            agent_input=raw.agent_input,
            question=raw.question,
            final_answer=raw.final_answer,
            phase_id=raw.phase_id,
            phase_title=raw.phase_title,
            risk=raw.risk,
            requires_confirmation=raw.requires_confirmation,
        )

    @staticmethod
    def _thinking_summary_payload(raw: PlannerThinkingOutput) -> Dict[str, Any]:
        return {
            "stepKind": "thinking",
            "execution_mode": ExecutionMode.THINKING.value,
            "hypotheses": [
                {
                    "summary": item.summary,
                    "rationale": item.fit,
                    "risks": list(item.risks or []),
                    "expected_outcome": item.expected_outcome,
                }
                for item in raw.hypotheses
            ],
            "selected_hypothesis_index": raw.selected_hypothesis_index,
            "selected_action_kind": raw.selected_action_kind,
            "selected_action_summary": raw.selected_action_summary,
            "selection_rationale": raw.selection_rationale,
        }

    @staticmethod
    def _thinking_system_prompt() -> str:
        return (
            "You are the planner in bounded thinking mode.\n"
            "Before choosing the next runtime action, generate 2 or 3 concise next-step hypotheses only.\n"
            "For each hypothesis provide: summary, expected_outcome, risks, fit.\n"
            "Select exactly one hypothesis and return its index, selected_action_kind, selected_action_summary, and selection_rationale.\n"
            "Do not produce hidden chain-of-thought, long prose, or user-facing answer text."
        )

    @staticmethod
    def _safe_fallback(
        runtime_state: Optional[RuntimeTurnState],
        reason: Optional[str],
    ) -> NextStep:
        has_facts = bool(runtime_state and runtime_state.runtime_facts)
        if has_facts:
            return NextStep(
                kind=NextStepKind.FINAL,
                rationale=f"forced_finalize_after_planner_failure: {reason or 'unknown'}",
                final_answer="(to be synthesized from collected facts)",
                phase_id=runtime_state.current_phase_id if runtime_state else "main",
            )
        return NextStep(
            kind=NextStepKind.ABORT,
            rationale=f"planner_failed_no_facts: {reason or 'unknown'}",
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        raw = (text or "").strip()
        if not raw:
            return 0
        # Heuristic fallback when provider usage is unavailable.
        return max(1, len(raw) // 4)
