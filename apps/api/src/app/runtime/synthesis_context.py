"""Canonical, final-plan-owned input for a synthesis checkpoint."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from app.runtime.orchestrator_contracts import PlanNodeKind, TaskStatus
from app.runtime.redactor import RuntimeRedactor


DEFAULT_SYNTHESIS_CONTEXT_MAX_CHARS = 120_000


class SynthesisContextError(ValueError):
    """A final-plan report cannot safely fit in one synthesis prompt."""


class SynthesisContextBuilder:
    """Build a complete, redacted report from the current persisted plan.

    This deliberately does not infer a dependency closure.  The final plan is
    the planner's authoritative selection: every current, successful work task
    is evidence for the terminal synthesis checkpoint.
    """

    def __init__(self, *, max_chars: int = DEFAULT_SYNTHESIS_CONTEXT_MAX_CHARS) -> None:
        self._max_chars = max(1, int(max_chars))
        self._redactor = RuntimeRedactor()

    def build(self, *, plan: Dict[str, Any], synthesis_task_id: str) -> Dict[str, Any]:
        tasks = dict(plan.get("tasks") or {})
        synthesis_task = tasks.get(synthesis_task_id)
        if not isinstance(synthesis_task, dict):
            raise SynthesisContextError("synthesis checkpoint is missing from the persisted plan")

        reports: List[Dict[str, Any]] = []
        artifacts: List[Dict[str, Any]] = []
        sources: List[Dict[str, Any]] = []
        for task_id, task in sorted(
            tasks.items(), key=lambda item: (int(item[1].get("planned_order", 0)), item[0])
        ):
            if task_id == synthesis_task_id:
                continue
            if task.get("kind") != PlanNodeKind.AGENT.value:
                continue
            if task.get("status") != TaskStatus.COMPLETED.value:
                continue
            result = task.get("result")
            if not isinstance(result, dict):
                raise SynthesisContextError(f"completed task {task_id} has no canonical result")
            verified = result.get("verified") if isinstance(result.get("verified"), dict) else {}
            reports.append({
                "task_id": str(task_id),
                "intent": self._redact(task.get("intent")),
                "instructions": self._redact(task.get("instructions")),
                "report": {
                    "description": self._redact(result.get("description") or result.get("summary")),
                    # Artifact references are accepted only through the
                    # runtime-verified metadata projection below; an agent's
                    # textual result cannot claim a downloadable file.
                    "outputs": self._report_outputs(result.get("outputs")),
                },
            })
            artifacts.extend(self._artifact_projection(verified.get("artifacts")))
            sources.extend(self._source_projection(verified.get("sources")))

        context = {
            "synthesis_task": {
                "task_id": str(synthesis_task_id),
                "intent": self._redact(synthesis_task.get("intent")),
                "instructions": self._redact(synthesis_task.get("instructions")),
            },
            "completed_task_reports": reports,
            "artifacts": self._dedupe(artifacts, "artifact_id"),
            "sources": self._dedupe(sources, "source_id"),
        }
        encoded = json.dumps(context, ensure_ascii=False, default=str)
        if len(encoded) > self._max_chars:
            raise SynthesisContextError(
                f"final-plan synthesis context exceeds the configured limit of {self._max_chars} characters"
            )
        return context

    def _redact(self, value: Any) -> Any:
        return self._redactor.redact(value)

    def _report_outputs(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        projected: Dict[str, Any] = {}
        for key, raw in value.items():
            if not isinstance(raw, dict):
                projected[str(key)] = self._redact(raw)
                continue
            output = {
                field: raw[field]
                for field in ("description", "text", "data")
                if field in raw
            }
            projected[str(key)] = self._redact(output)
        return projected

    @staticmethod
    def _artifact_projection(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [
            {
                "artifact_id": str(item.get("artifact_id") or "").strip(),
                "file_name": item.get("file_name") or item.get("name") or "file",
                "content_type": item.get("content_type") or "",
                "size_bytes": item.get("size_bytes"),
            }
            for item in value
            if isinstance(item, dict) and str(item.get("artifact_id") or "").strip()
        ]

    @staticmethod
    def _source_projection(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        result: List[Dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or item.get("id") or item.get("url") or "").strip()
            if source_id:
                # Sources are citation/delivery metadata. Do not smuggle raw
                # retrieval payloads into the synthesis input.
                projected = {"source_id": source_id}
                source_name = item.get("source_name") or item.get("title") or item.get("name")
                if source_name:
                    projected["source_name"] = source_name
                if item.get("url"):
                    projected["url"] = item["url"]
                result.append(projected)
        return result

    @staticmethod
    def _dedupe(items: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        return [
            item for item in items
            if (identifier := str(item.get(key) or "").strip())
            and not (identifier in seen or seen.add(identifier))
        ]
