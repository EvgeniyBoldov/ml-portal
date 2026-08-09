"""Runtime input builders for planner/synthesizer surfaces."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.runtime.turn_state import RuntimeTurnState


MAX_CONVERSATION_SUMMARY_CHARS = 3000
MAX_POLICIES_TEXT_CHARS = 1200
MAX_AGENT_DESCRIPTION_CHARS = 280


class PlannerInputBuilder:
    """Build structured planner payload from runtime state."""

    def build_graph_request(self, request: Any) -> Dict[str, Any]:
        """Canonical compact payload for graph planning and replanning.

        Keep this intentionally independent from ``RuntimeTurnState`` so the
        planner can be resumed from a persisted plan in a worker process.
        """
        agents = []
        for item in request.available_agents or []:
            if not item.get("slug"):
                continue
            agents.append({
                "slug": item.get("slug"),
                "description": self._trim_text(item.get("description", ""), MAX_AGENT_DESCRIPTION_CHARS),
                "tags": list(item.get("tags") or []),
                "provides_keys": list(item.get("provides_keys") or []),
            })
        plan = dict(request.plan or {})
        tasks = plan.get("tasks") if isinstance(plan.get("tasks"), dict) else {}
        planner_plan = {
            "has_existing_graph": bool(tasks) or int(plan.get("revision") or 0) > 0,
            "status": plan.get("status"),
            "tasks": tasks,
        }
        payload = {
            "goal": request.goal,
            "mode": "replan" if planner_plan["has_existing_graph"] else "initial",
            "replan_reason": request.trigger,
            "plan": planner_plan,
            "completed_outputs": request.completed_outputs or {},
            "available_artifacts": self._normalize_artifacts(request.available_artifacts or []),
            "needs": request.needs or [],
            "last_failure": request.last_failure,
            "memory_context": request.memory_context or [],
            "available_agents": agents,
        }
        user_response = str(getattr(request, "user_response", "") or "").strip()
        if user_response:
            payload["user_response"] = user_response
        return payload

    def build(
        self,
        *,
        runtime_state: RuntimeTurnState,
        available_agents: List[Dict[str, Any]],
        outline: Optional[Dict[str, Any]],
        platform_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        state = runtime_state

        # Conversation context from memory_bundle if available
        conversation_summary = ""
        if state.memory_bundle and state.memory_bundle.sections:
            for section in state.memory_bundle.sections:
                if section.name == "conversation" and section.items:
                    conversation_summary = section.items[0].text[:MAX_CONVERSATION_SUMMARY_CHARS]
                    break

        # Collect pending needs for routing
        pending_needs = state.pending_needs()

        # Build task journal compact view (last 10 items)
        task_journal_summary: List[Dict[str, Any]] = []
        for t in state.task_journal[-10:]:
            task_journal_summary.append({
                "task_id": t.task_id,
                "title": t.title,
                "assigned_agent": t.assigned_agent,
                "status": t.status,
                "needs": [{"ref": n.ref, "key": n.key, "status": n.status} for n in t.needs],
            })

        return {
            "goal": state.goal,
            "current_user_query": state.current_user_query,
            "execution_mode": state.execution_mode.value,
            "attachments": [
                {
                    "file_name": item.ref.file_name,
                    "artifact_id": item.ref.artifact_id,
                    "content_type": item.ref.content_type,
                    "size_bytes": item.ref.size_bytes,
                    "snippet": item.snippet,
                    "snippet_status": item.snippet_status,
                    "readable": item.readable,
                    "truncated": item.truncated,
                }
                for item in (state.attachment_contexts or [])
            ],
            "conversation_summary": conversation_summary,
            "continuation": dict(state.continuation or {}) or None,
            "available_agents": [
                {
                    "slug": item.get("slug"),
                    "description": self._trim_text(
                        item.get("description", ""),
                        MAX_AGENT_DESCRIPTION_CHARS,
                    ),
                    "tags": list(item.get("tags") or []),
                    "provides_keys": list(item.get("provides_keys") or []),
                    **(
                        {
                            "capability_summary": self._trim_text(
                                item.get("capability_summary", ""),
                                MAX_AGENT_DESCRIPTION_CHARS,
                            )
                        }
                        if item.get("capability_summary")
                        else {}
                    ),
                    **(
                        {"collections": list(item.get("collections") or [])}
                        if item.get("collections")
                        else {}
                    ),
                    **(
                        {"system_operations": list(item.get("system_operations") or [])}
                        if item.get("system_operations")
                        else {}
                    ),
                }
                for item in available_agents
                if item.get("slug")
            ],
            "execution_outline": outline,
            "memory": state.planner_snapshot(),
            "last_iteration_result": (
                state.iteration_results[-1].model_dump()
                if state.iteration_results
                else None
            ),
            "task_journal": task_journal_summary,
            "pending_needs": [
                {"ref": n.ref, "key": n.key, "description": n.description}
                for n in pending_needs[-10:]
            ],
            "policies": self._trim_text(
                (platform_config or {}).get("policies_text") or "default",
                MAX_POLICIES_TEXT_CHARS,
            ),
        }

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
    """Build user-facing synthesis prompt from runtime state."""

    def build(
        self,
        *,
        runtime_state: RuntimeTurnState,
        answer_brief: Optional[str],
        system_prompt: str,
    ) -> List[Dict[str, str]]:
        state = runtime_state

        rag_sources: List[Dict[str, Any]] = []
        if state.memory_bundle and state.memory_bundle.sections:
            for section in state.memory_bundle.sections:
                if section.name == "sources" and section.items:
                    for item in section.items[:20]:
                        if isinstance(item.metadata, dict) and isinstance(item.metadata.get("source"), dict):
                            rag_sources.append(dict(item.metadata["source"]))

        generated_files: List[Dict[str, Any]] = []
        for item in state.agent_results:
            item_attachments = item.get("attachments")
            if isinstance(item_attachments, list):
                for att in item_attachments[-10:]:
                    if not isinstance(att, dict):
                        continue
                    generated_files.append(
                        {
                            "artifact_id": att.get("artifact_id"),
                            "file_name": att.get("file_name") or att.get("name") or "file",
                            "content_type": att.get("content_type") or "",
                            "size_bytes": att.get("size_bytes"),
                        }
                    )

        unique_files: List[Dict[str, Any]] = []
        seen_artifacts: set[str] = set()
        for item in generated_files:
            artifact_id = str(item.get("artifact_id") or "").strip()
            if (
                not artifact_id
                or item.get("status") == "deleted"
                or artifact_id in state.deleted_artifact_ids
                or artifact_id in seen_artifacts
            ):
                continue
            seen_artifacts.add(artifact_id)
            unique_files.append(item)

        # Build task journal summary for synthesizer
        task_journal_summary = []
        for t in state.task_journal:
            task_journal_summary.append({
                "task_id": t.task_id,
                "title": t.title,
                "assigned_agent": t.assigned_agent,
                "status": t.status,
                "summary": t.summary,
            })

        payload: Dict[str, Any] = {
            "answer_brief": str(answer_brief or state.answer_brief or "").strip(),
            "generated_files": unique_files[-10:],
            "rag_sources": rag_sources[:20],
            "task_journal": task_journal_summary,
            "language_hint": self._detect_language_hint(state.current_user_query or state.goal or ""),
            "style_constraints": {
                "concise": True,
                "preserve_lists": True,
                "preserve_order": True,
            },
        }

        import json

        user_content = json.dumps(payload, ensure_ascii=False, default=str, indent=2)

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _detect_language_hint(text: str) -> Optional[str]:
        sample = str(text or "").strip()
        if not sample:
            return None
        if re.search(r"[А-Яа-яЁё]", sample):
            return "ru"
        return None
