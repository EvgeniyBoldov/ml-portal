"""LLM-backed graph planner.

This is deliberately a small decision engine: it proposes a complete graph
mutation, while the orchestrator validates and executes that mutation.  It
never invokes an agent or a tool itself.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.http.clients import LLMClientProtocol
from app.models.system_llm_role import SystemLLMRoleType
from app.runtime.llm.structured import StructuredCallError, StructuredLLMCall
from app.runtime.orchestrator_contracts import PlanPatch, PlanRequest
from app.runtime.input_builders import PlannerInputBuilder


class PlannerGraphOutput(BaseModel):
    """Strict wire format returned by the planner role."""

    decision: Literal["create_plan", "revise_plan", "ask_user", "complete_plan", "fail_plan"]
    expected_revision: int = Field(..., ge=0)
    rationale: str = ""
    goal: Optional[str] = None
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    remove_task_ids: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    answer_brief: Optional[str] = None
    failure_reason: Optional[str] = None
    trigger: Optional[str] = None


class GraphPlanner:
    """Planner adapter backed by ``StructuredLLMCall``."""

    def __init__(self, *, session: Any, llm_client: LLMClientProtocol, observation_writer: Optional[Any] = None) -> None:
        self._llm = StructuredLLMCall(session=session, llm_client=llm_client)
        self._input_builder = PlannerInputBuilder()

    async def plan(
        self,
        *,
        request: PlanRequest,
        chat_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        agent_run_id: Optional[UUID] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> PlanPatch:
        payload = self._input_builder.build_graph_request(request)
        result = await self._llm.invoke(
            role=SystemLLMRoleType.PLANNER,
            payload=payload,
            schema=PlannerGraphOutput,
            chat_id=chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_run_id=agent_run_id,
            sandbox_overrides=sandbox_overrides,
        )
        try:
            return PlanPatch.model_validate(self._normalise_patch(result.value.model_dump(mode="json")))
        except Exception as exc:  # validation is a planner protocol failure
            raise StructuredCallError(
                f"planner returned an invalid graph patch: {exc}",
                original_exception=exc,
            ) from exc

    @staticmethod
    def _normalise_patch(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize harmless weak-model variations at the planner boundary.

        ``PlannerGraphOutput`` intentionally remains permissive so structured
        providers can return JSON without reproducing every nested contract
        detail.  Before crossing into the orchestrator, however, the strict
        ``PlanPatch`` contract must be satisfied.  Empty optional strings and
        shorthand output/requirement descriptions are common model outputs
        and have an unambiguous canonical representation.
        """
        normalized = dict(payload)
        for key in ("goal", "question", "answer_brief", "failure_reason", "trigger"):
            if normalized.get(key) == "":
                normalized[key] = None

        tasks = normalized.get("tasks")
        if not isinstance(tasks, list):
            return normalized

        canonical_tasks: list[dict[str, Any]] = []
        for raw_task in tasks:
            if not isinstance(raw_task, dict):
                canonical_tasks.append(raw_task)
                continue
            task = dict(raw_task)
            # Some providers follow the shorter task vocabulary from the
            # examples (id/name/description) even when the JSON schema uses
            # the canonical task_id/title/objective names.
            if not task.get("task_id") and task.get("id"):
                task["task_id"] = task["id"]
            if not task.get("title"):
                task["title"] = task.get("name") or task.get("label")
            if not task.get("objective"):
                task["objective"] = task.get("description") or task.get("title")
            # Accept the concise ``agent`` spelling, while keeping the
            # persisted contract explicit about the routed agent.
            if not task.get("agent_slug") and task.get("agent"):
                task["agent_slug"] = task.pop("agent")

            if task.get("depends_on") is None and task.get("dependencies") is not None:
                task["depends_on"] = task["dependencies"]
            if task.get("expected_outputs") is None and task.get("outputs") is not None:
                task["expected_outputs"] = task["outputs"]

            outputs = task.get("expected_outputs")
            if isinstance(outputs, dict):
                outputs = [
                    {
                        "key": key,
                        "description": (
                            value.get("description")
                            if isinstance(value, dict) and value.get("description")
                            else str(value or key)
                        ),
                        **(
                            {"schema": value.get("schema")}
                            if isinstance(value, dict) and isinstance(value.get("schema"), dict)
                            else {}
                        ),
                    }
                    for key, value in outputs.items()
                ]
            if isinstance(outputs, list):
                task["expected_outputs"] = [
                    {
                        "key": f"output_{index + 1}",
                        "description": item,
                    }
                    if isinstance(item, str) else item
                    for index, item in enumerate(outputs)
                ]

            requirements = task.get("requirements")
            if isinstance(requirements, dict):
                requirements = [
                    {
                        "key": key,
                        "description": (
                            value.get("description")
                            if isinstance(value, dict) and value.get("description")
                            else str(value or key)
                        ),
                        **(
                            {"required": bool(value.get("required"))}
                            if isinstance(value, dict) and "required" in value
                            else {}
                        ),
                    }
                    for key, value in requirements.items()
                ]
            if isinstance(requirements, list):
                task["requirements"] = [
                    {
                        "key": item,
                        "description": item,
                    }
                    if isinstance(item, str) else item
                    for item in requirements
                ]
            canonical_tasks.append(task)
        normalized["tasks"] = canonical_tasks
        return normalized

    async def create_or_revise(self, *, request: PlanRequest) -> PlanPatch:
        return await self.plan(request=request)
