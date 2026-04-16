from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.contracts import ExecutionModeType, ExecutionOutline, OutlinePhase

# Defaults used when platform config does not provide overrides
_DEFAULT_MAX_ITERATIONS = 12
_DEFAULT_MAX_AGENT_HANDOFFS = 5
_DEFAULT_FINALIZATION_RULES = [
    "Do not finalize until all required phases are complete.",
    "If evidence is insufficient after required checks, ask the user for clarification instead of guessing.",
]
_DEFAULT_CLARIFY_TRIGGERS = [
    "The target object is ambiguous.",
    "Required source material cannot be identified.",
]


class ExecutionOutlineService:
    """Builds phased execution outline for orchestrated runtime flows.

    Configurable parameters are read from platform_config at call time
    so they can be managed via AdminUI / PlatformSettings without code changes.
    """

    def build(
        self,
        *,
        request_text: str,
        triage_result: Dict[str, object],
        available_agent_slugs: List[str],
        platform_config: Optional[Dict[str, Any]] = None,
    ) -> ExecutionOutline:
        cfg = platform_config or {}

        max_iterations = cfg.get("abs_max_plan_steps") or _DEFAULT_MAX_ITERATIONS
        max_agent_handoffs = cfg.get("abs_max_concurrency") or _DEFAULT_MAX_AGENT_HANDOFFS

        lowered = request_text.lower()
        needs_comparison = any(token in lowered for token in ("compare", "сравн", "difference", "разниц"))
        needs_knowledge_search = any(token in lowered for token in (
            "регламент", "policy", "документ", "документац",
            "инструкци", "процесс", "политик", "восстановлен", "сбо",
            "безопасност", "регулировани", "найди", "найти", "поиск",
            "покажи", "какие есть",
        ))

        phases: List[OutlinePhase] = []

        # First phase: always search/retrieve via agents (not ask_user)
        knowledge_agents = [
            slug for slug in available_agent_slugs
            if any(token in slug for token in ("knowledge", "search", "document", "policy"))
        ]
        phases.append(
            OutlinePhase(
                phase_id="search_and_retrieve",
                title="Search and retrieve relevant information",
                objective=(
                    "Use available agents to search the knowledge base, documents, "
                    "or systems for information relevant to the user's request. "
                    "Always delegate to an agent — do NOT ask the user."
                ),
                must_do=True,
                preferred_agents=knowledge_agents if needs_knowledge_search else (available_agent_slugs[:1] if available_agent_slugs else []),
                preferred_sources=[],
                completion_signals=["relevant data retrieved", "search completed"],
                allow_final_after=False,
            )
        )

        if needs_comparison:
            phases.append(
                OutlinePhase(
                    phase_id="compare_findings",
                    title="Compare findings",
                    objective="Compare gathered facts and identify similarities, differences, or contradictions.",
                    must_do=True,
                    completion_signals=["comparison completed", "differences captured"],
                    allow_final_after=False,
                )
            )

        phases.append(
            OutlinePhase(
                phase_id="finalize",
                title="Finalize answer",
                objective="Provide the final answer only after all required investigation phases are complete.",
                must_do=True,
                completion_signals=["final answer ready"],
                allow_final_after=True,
            )
        )

        mode = ExecutionModeType.MULTI_AGENT if len(available_agent_slugs) > 1 else ExecutionModeType.SINGLE_AGENT
        suggested_start_agent = (
            next(
                (
                    slug for slug in available_agent_slugs
                    if any(token in slug for token in ("knowledge", "search", "document", "policy"))
                ),
                None,
            )
            if needs_knowledge_search
            else (available_agent_slugs[0] if available_agent_slugs else None)
        )

        return ExecutionOutline(
            mode=mode,
            goal=str(triage_result.get("goal") or request_text),
            suggested_start_agent=suggested_start_agent,
            phases=phases,
            finalization_rules=_DEFAULT_FINALIZATION_RULES,
            clarify_triggers=_DEFAULT_CLARIFY_TRIGGERS,
            max_iterations=max_iterations,
            max_agent_handoffs=max_agent_handoffs,
        )
