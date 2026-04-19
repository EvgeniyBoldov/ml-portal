"""
Triage — decision #1 of the pipeline.

Outputs a single `TriageDecision`:
    * final       — answer directly, no planning needed
    * clarify     — ask for missing info before planning
    * orchestrate — normalize goal and hand off to planner
    * resume      — user answered an open_question of a paused run; continue that run

Memory awareness:
    Triage receives `WorkingMemory.triage_snapshot()` from the most recent run
    of the chat (if any). If that run is paused with open_questions and the
    user's new text looks like an answer, triage may emit `resume`.

Schema contract: LLM must return JSON matching TriageLLMOutput below. We then
normalize it into the final `TriageDecision` that downstream code uses.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.contracts import TriageDecision, TriageIntent
from app.runtime.llm.structured import StructuredLLMCall, StructuredCallError
from app.runtime.memory.working_memory import WorkingMemory

logger = get_logger(__name__)


class TriageLLMOutput(BaseModel):
    """Raw LLM schema. Matches the prompt's output_requirements."""

    type: Literal["final", "clarify", "orchestrate", "resume"]
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: Optional[str] = None
    answer: Optional[str] = None
    clarify_prompt: Optional[str] = None
    goal: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    agent_hint: Optional[str] = None
    resume_run_id: Optional[str] = None


class Triage:
    """Runs a single LLM call to classify the incoming request."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.llm = StructuredLLMCall(session=session, llm_client=llm_client)

    async def decide(
        self,
        *,
        request_text: str,
        memory: WorkingMemory,
        routable_agents: List[Dict[str, Any]],
        paused_runs: List[WorkingMemory],
        platform_config: Optional[Dict[str, Any]] = None,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> TriageDecision:
        payload = {
            "user_message": request_text,
            "conversation_summary": memory.dialogue_summary or "",
            "session_state": memory.triage_snapshot(),
            "available_agents": routable_agents,
            "paused_runs": [
                {
                    "run_id": str(paused.run_id),
                    "goal": paused.goal,
                    "open_questions": list(paused.open_questions),
                    "last_agent": paused.current_agent_slug,
                }
                for paused in paused_runs
            ],
            "policies": (platform_config or {}).get("policies_text") or "default",
        }

        try:
            result = await self.llm.invoke(
                role=SystemLLMRoleType.TRIAGE,
                # system_prompt left unset → StructuredLLMCall loads the
                # compiled prompt from the active TRIAGE system_llm_roles row.
                payload=payload,
                schema=TriageLLMOutput,
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                fallback_factory=self._fallback,
            )
        except StructuredCallError as exc:
            logger.warning("Triage failed, using safe fallback: %s", exc)
            return self._safe_fallback(request_text)

        return self._normalize(result.value, paused_runs=paused_runs)

    # --------------------------------------------------------------- helpers --

    @staticmethod
    def _normalize(
        output: TriageLLMOutput,
        *,
        paused_runs: List[WorkingMemory],
    ) -> TriageDecision:
        intent_map = {
            "final": TriageIntent.FINAL,
            "clarify": TriageIntent.CLARIFY,
            "orchestrate": TriageIntent.ORCHESTRATE,
            "resume": TriageIntent.RESUME,
        }
        intent = intent_map[output.type]

        # Validate consistency
        if intent == TriageIntent.FINAL and not (output.answer or "").strip():
            # LLM said final but forgot the answer — downgrade to orchestrate
            intent = TriageIntent.ORCHESTRATE

        if intent == TriageIntent.CLARIFY and not (output.clarify_prompt or "").strip():
            # Fallback: generic clarify
            output.clarify_prompt = "Could you provide more details about what you need?"

        resume_run_id: Optional[UUID] = None
        if intent == TriageIntent.RESUME:
            candidate = output.resume_run_id
            try:
                parsed_uuid = UUID(candidate) if candidate else None
            except (TypeError, ValueError):
                parsed_uuid = None
            if parsed_uuid and any(paused.run_id == parsed_uuid for paused in paused_runs):
                resume_run_id = parsed_uuid
            elif paused_runs:
                # LLM signalled resume but picked a non-existent id; fall back to latest paused
                resume_run_id = paused_runs[0].run_id
            else:
                # No paused run to resume → treat as orchestrate
                intent = TriageIntent.ORCHESTRATE

        return TriageDecision(
            intent=intent,
            confidence=output.confidence,
            goal=(output.goal or "").strip() or None,
            answer=(output.answer or "").strip() or None,
            clarify_prompt=(output.clarify_prompt or "").strip() or None,
            resume_run_id=resume_run_id,
            agent_hint=(output.agent_hint or "").strip() or None,
            reason=(output.reason or "").strip() or None,
        )

    @staticmethod
    def _fallback(raw_response: str) -> TriageLLMOutput:
        """Invoked by StructuredLLMCall when schema validation fails across retries.
        Returns a conservative orchestrate decision so the pipeline can still proceed."""
        return TriageLLMOutput(
            type="orchestrate",
            confidence=0.3,
            reason="triage_fallback_used",
        )

    @staticmethod
    def _safe_fallback(request_text: str) -> TriageDecision:
        """Last-ditch fallback when even StructuredLLMCall bails out entirely.
        Happens only if LLM is completely broken; we send the user a clarify."""
        return TriageDecision(
            intent=TriageIntent.ORCHESTRATE,
            confidence=0.2,
            goal=request_text[:500],
            reason="triage_safe_fallback",
        )
