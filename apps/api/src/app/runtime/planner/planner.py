"""
Planner — decides the next step of the run.

Key properties:
    * Planner talks only to **agents**, never to operations/tools directly.
    * Stateless: each call reads WorkingMemory and produces one NextStep.
    * Output is strictly validated; invalid decisions trigger a single retry
      with an explicit error message prepended to the payload.

The seed prompt (see app.runtime.seeds.system_roles) enforces the schema below
in `output_requirements`. The model field names in the prompt must match.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.contracts import NextStep, NextStepKind
from app.runtime.llm.structured import StructuredLLMCall, StructuredCallError
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.planner.prompt import PLANNER_SYSTEM_PROMPT
from app.runtime.planner.validator import validate_next_step

logger = get_logger(__name__)


class PlannerLLMOutput(BaseModel):
    """Schema the planner LLM is required to produce."""

    kind: Literal["call_agent", "ask_user", "final", "abort"]
    rationale: str = Field(..., min_length=1)
    agent_slug: Optional[str] = None
    agent_input: Dict[str, Any] = Field(default_factory=dict)
    question: Optional[str] = None
    final_answer: Optional[str] = None
    phase_id: Optional[str] = None
    phase_title: Optional[str] = None
    risk: Literal["low", "medium", "high"] = "low"
    requires_confirmation: bool = False


class Planner:
    """One-LLM-call next-step planner."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.llm = StructuredLLMCall(session=session, llm_client=llm_client)

    async def next_step(
        self,
        *,
        memory: WorkingMemory,
        available_agents: List[Dict[str, Any]],
        outline: Optional[Dict[str, Any]] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        agent_run_id: Optional[UUID] = None,
    ) -> NextStep:
        allowed_slugs = [a.get("slug") for a in available_agents if a.get("slug")]
        payload_base = {
            "goal": memory.goal,
            "conversation_summary": memory.dialogue_summary or "",
            "available_agents": [
                {"slug": a.get("slug"), "description": a.get("description", "")}
                for a in available_agents
                if a.get("slug")
            ],
            "execution_outline": outline,
            "memory": memory.planner_snapshot(),
            "policies": (platform_config or {}).get("policies_text") or "default",
        }

        # First attempt — normal payload. On structural or validator failure, retry
        # once with an explicit error appended so the model can correct itself.
        last_error: Optional[str] = None
        for attempt in range(2):
            payload = dict(payload_base)
            if last_error:
                payload["previous_error"] = last_error

            try:
                result = await self.llm.invoke(
                    role=SystemLLMRoleType.PLANNER,
                    system_prompt=PLANNER_SYSTEM_PROMPT,
                    payload=payload,
                    schema=PlannerLLMOutput,
                    chat_id=chat_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_run_id=agent_run_id,
                )
            except StructuredCallError as exc:
                last_error = f"schema_error: {exc}"
                continue

            candidate = self._to_next_step(result.value)

            err = validate_next_step(
                candidate,
                allowed_agents=allowed_slugs,
                memory=memory,
            )
            if err is None:
                return candidate

            logger.info("Planner validation retry (attempt=%s): %s", attempt, err)
            last_error = err

        # Two attempts failed → safe forced finalize if we have facts, else abort.
        return self._safe_fallback(memory, last_error)

    # --------------------------------------------------------------- helpers --

    @staticmethod
    def _to_next_step(raw: PlannerLLMOutput) -> NextStep:
        kind_map = {
            "call_agent": NextStepKind.CALL_AGENT,
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
    def _safe_fallback(memory: WorkingMemory, reason: Optional[str]) -> NextStep:
        if memory.facts:
            return NextStep(
                kind=NextStepKind.FINAL,
                rationale=f"forced_finalize_after_planner_failure: {reason or 'unknown'}",
                final_answer="(to be synthesized from collected facts)",
                phase_id=memory.current_phase_id,
            )
        return NextStep(
            kind=NextStepKind.ABORT,
            rationale=f"planner_failed_no_facts: {reason or 'unknown'}",
        )
