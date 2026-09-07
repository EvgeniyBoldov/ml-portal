"""Runtime input builders for planner/synthesizer surfaces."""
from __future__ import annotations

from typing import Any, Dict, List


MAX_AGENT_DESCRIPTION_CHARS = 280


class PlannerInputBuilder:
    """Build the sole planner payload: the iterative execution ledger."""

    def build_graph_request(self, request: Any) -> Dict[str, Any]:
        """Canonical payload for every planner invocation."""
        context = request.context
        agents = []
        for item in context.available_agents or []:
            if not item.get("slug"):
                continue
            agents.append({
                "slug": item.get("slug"),
                "description": self._trim_text(item.get("description", ""), MAX_AGENT_DESCRIPTION_CHARS),
                "tags": list(item.get("tags") or []),
                "provides_keys": list(item.get("provides_keys") or []),
            })
        payload = {
            "goal": context.goal,
            "trigger": context.trigger,
            "execution_ledger": context.execution_ledger,
            "available_artifacts": self._normalize_artifacts(context.available_artifacts),
            "memory_context": context.memory_context,
            "available_agents": agents,
            "iteration_contract": {
                "tasks_are_agents_only": True,
                "terminal": ["planner", "synthesis"],
                "synthesis_requires_brief": True,
                "partial_results_require_resolution": True,
            },
        }
        return payload

    @staticmethod
    def _trim_text(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit]

    @staticmethod
    def _normalize_artifacts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            ref = item.get("ref") if isinstance(item.get("ref"), dict) else item
            artifact_id = str(ref.get("artifact_id") or item.get("artifact_id") or "").strip()
            if not artifact_id or artifact_id in seen:
                continue
            seen.add(artifact_id)
            result.append({
                "artifact_id": artifact_id,
                "file_name": ref.get("file_name") or item.get("file_name") or "artifact",
                "content_type": ref.get("content_type") or item.get("content_type"),
                "size_bytes": ref.get("size_bytes") or item.get("size_bytes"),
                "snippet": item.get("snippet") or "",
                "snippet_status": item.get("snippet_status") or "missing",
                "readable": bool(item.get("readable")),
                "truncated": bool(item.get("truncated")),
            })
        return result


class SynthesizerInputBuilder:
    """Render the already validated final-plan synthesis context."""

    def build(
        self,
        *,
        synthesis_context: Dict[str, Any],
        system_prompt: str,
    ) -> List[Dict[str, str]]:
        import json

        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(synthesis_context, ensure_ascii=False, default=str, indent=2),
            },
        ]
