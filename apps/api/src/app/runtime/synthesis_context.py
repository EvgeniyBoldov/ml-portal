"""Runtime-owned final evidence package for synthesis."""
from __future__ import annotations

import json
from typing import Any, Dict

from app.runtime.orchestrator_contracts import ResolutionAction, TaskStatus
from app.runtime.redactor import RuntimeRedactor
from app.runtime.memory.effective_scope import project_memory_context
from app.runtime.memory.execution_context import memory_execution_context


DEFAULT_SYNTHESIS_CONTEXT_MAX_CHARS = 120_000


class SynthesisContextError(ValueError):
    pass


class SynthesisContextBuilder:
    def __init__(self, *, max_chars: int = DEFAULT_SYNTHESIS_CONTEXT_MAX_CHARS) -> None:
        self._max_chars = max(1, int(max_chars))
        self._redactor = RuntimeRedactor()

    def build(
        self, *, plan: Dict[str, Any], iteration_id: str,
        deleted_artifact_ids: list[str] | None = None,
    ) -> Dict[str, Any]:
        iteration = next((item for item in plan.get("iterations", []) if item.get("id") == iteration_id), None)
        if not isinstance(iteration, dict) or not isinstance(iteration.get("synthesis_brief"), dict):
            raise SynthesisContextError("claimed synthesis iteration has no synthesis brief")
        tasks = dict(plan.get("tasks") or {})
        iteration_order = {str(item.get("id")): int(item.get("sequence") or 0) for item in plan.get("iterations", [])}
        latest_resolutions: Dict[str, Dict[str, Any]] = {}
        for item in list(plan.get("resolutions") or []):
            task_id = str(item.get("task_id") or "")
            if task_id:
                latest_resolutions[task_id] = item
        resolutions = list(latest_resolutions.values())
        resolved = {
            task_id
            for task_id, item in latest_resolutions.items()
            if item.get("action") in {
                ResolutionAction.ACCEPT_PARTIAL.value,
                ResolutionAction.EXCLUDE_FROM_SCOPE.value,
            }
        }
        for item in resolutions:
            if item.get("action") == ResolutionAction.CONTINUE_WITH_TASKS.value and all(
                tasks.get(task_id, {}).get("status") == TaskStatus.COMPLETED.value
                for task_id in item.get("replacement_task_ids", [])
            ):
                resolved.add(str(item["task_id"]))
        reports, limitations, artifacts, sources = [], [], [], []
        for task_id, task in sorted(tasks.items(), key=lambda pair: (iteration_order.get(str(pair[1].get("iteration_id")), 0), pair[1].get("planned_order", 0), pair[0])):
            result = task.get("result") if isinstance(task.get("result"), dict) else {}
            status = str(task.get("status") or "")
            outputs = result.get("outputs") if isinstance(result.get("outputs"), dict) else {}
            excluded = latest_resolutions.get(task_id, {}).get("action") == ResolutionAction.EXCLUDE_FROM_SCOPE.value
            if result and not excluded:
                verified = result.get("verified") if isinstance(result.get("verified"), dict) else {}
                reports.append({"task_id": task_id, "intent": self._redact(task.get("intent")),
                                "status": status, "completion": result.get("completion"),
                                "description": self._redact(result.get("answer") or result.get("description")),
                                "answer": self._redact(result.get("answer", result.get("description"))),
                                "structured_response": self._redact(result.get("structured_response", outputs)),
                                "outputs": self._redact(outputs), "needs": self._redact(result.get("needs", [])),
                                "diagnostics": self._redact(result.get("diagnostics", []))})
                artifacts.extend(self._artifact_projection(result.get("attachments") or verified.get("artifacts")))
                sources.extend(self._source_projection(result.get("sources") or verified.get("sources")))
            if status != TaskStatus.COMPLETED.value and task_id not in resolved:
                limitation = result.get("limitation") if isinstance(result.get("limitation"), dict) else {}
                limitations.append({"task_id": task_id, "status": status, "reason_code": self._redact(limitation.get("code") or result.get("reason_code")), "message": self._redact(limitation.get("message") or result.get("description") or "Task did not complete")})
        deleted = {str(item) for item in deleted_artifact_ids or [] if str(item)}
        deliverable_artifacts = [
            item for item in self._dedupe(artifacts, "artifact_id")
            if str(item.get("artifact_id") or "") not in deleted
        ]
        allowed_scope = set((plan.get("scope_context") or {}).get("keys") or [])
        memory_context = []
        for item in plan.get("memory_context") or []:
            if not isinstance(item, dict) or item.get("type") not in {"memory_recall", "planner_memory_result"}:
                continue
            memory_context.append(project_memory_context(item, allowed_scope))
        context = {"user_question": plan.get("goal"), "synthesis_brief": self._redact(iteration["synthesis_brief"]), "plan_outline": [{"sequence": item.get("sequence"), "terminal": item.get("terminal")} for item in plan.get("iterations", [])], "resolution_decisions": self._redact([{key: item.get(key) for key in ("task_id", "action", "output_keys", "reason")} for item in resolutions if item.get("action") != ResolutionAction.CONTINUE_WITH_TASKS.value]), "completed_task_reports": reports, "limitations": limitations, "memory_context": self._redact(memory_context), "artifacts": deliverable_artifacts, "sources": self._dedupe(sources, "source_id")}
        context["scope_context"] = self._redact(plan.get("scope_context") or {})
        context["execution_context"] = memory_execution_context(
            sorted(allowed_scope), revision=int((plan.get("scope_context") or {}).get("revision") or 0),
        )
        return self._compact_to_limit(context)

    def _compact_to_limit(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Never lose a completed plan merely because evidence is verbose."""
        if len(json.dumps(context, ensure_ascii=False, default=str)) <= self._max_chars:
            return context

        def compact(value: Any, depth: int = 0) -> Any:
            if isinstance(value, str):
                return value if len(value) <= 1_024 else value[:1_024] + "…[truncated]"
            if isinstance(value, list):
                result = [compact(item, depth + 1) for item in value[:40]]
                if len(value) > 40:
                    result.append({"_truncated_items": len(value) - 40})
                return result
            if isinstance(value, dict):
                if depth > 8:
                    return {"_truncated": "nested value omitted"}
                return {str(key): compact(item, depth + 1) for key, item in list(value.items())[:80]}
            return value

        bounded = compact(context)
        # Delivery metadata is runtime-owned and must survive context compaction.
        bounded["artifacts"] = context["artifacts"]
        bounded["sources"] = context["sources"]
        while bounded.get("memory_context") and len(json.dumps(bounded, ensure_ascii=False, default=str)) > self._max_chars:
            memories = bounded["memory_context"]
            # Preserve turn recall first; trim the oldest planner reads before
            # sacrificing verified task outputs to accumulated search history.
            index = 1 if len(memories) > 1 and memories[0].get("type") == "memory_recall" else 0
            memories.pop(index)
            bounded["memory_context_truncated"] = True
        for report in bounded.get("completed_task_reports", []):
            if len(json.dumps(bounded, ensure_ascii=False, default=str)) <= self._max_chars:
                break
            if isinstance(report, dict) and report.get("outputs"):
                report["outputs"] = {"_truncated": "full value retained in task journal"}
                report["structured_response"] = {"_truncated": "full value retained in task journal"}
        if len(json.dumps(bounded, ensure_ascii=False, default=str)) > self._max_chars:
            bounded["completed_task_reports"] = [
                {key: report.get(key) for key in ("task_id", "intent", "status", "completion", "description")}
                for report in bounded.get("completed_task_reports", []) if isinstance(report, dict)
            ]
        if len(json.dumps(bounded, ensure_ascii=False, default=str)) > self._max_chars:
            raise SynthesisContextError("synthesis context exceeds configured size after compaction")
        return bounded

    def _redact(self, value: Any) -> Any:
        return self._redactor.redact(value)

    def _artifact_projection(self, value: Any) -> list[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [
            self._redact({
                "artifact_id": str(item.get("artifact_id") or "").strip(),
                "file_name": item.get("file_name") or item.get("name") or "file",
                "content_type": item.get("content_type") or "",
                "size_bytes": item.get("size_bytes"),
            })
            for item in value
            if isinstance(item, dict) and str(item.get("artifact_id") or "").strip()
        ]

    def _source_projection(self, value: Any) -> list[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        projected: list[Dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or item.get("id") or item.get("url") or "").strip()
            if not source_id:
                continue
            source = {"source_id": source_id}
            if item.get("source_name") or item.get("title") or item.get("name"):
                source["source_name"] = item.get("source_name") or item.get("title") or item.get("name")
            if item.get("url"):
                source["url"] = item["url"]
            projected.append(self._redact(source))
        return projected

    @staticmethod
    def _dedupe(items: list[Any], key: str) -> list[Dict[str, Any]]:
        seen: set[str] = set()
        output: list[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and (value := str(item.get(key) or "")) and value not in seen:
                seen.add(value)
                output.append(item)
        return output
