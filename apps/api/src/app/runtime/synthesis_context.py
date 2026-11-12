"""Runtime-owned final evidence package for synthesis."""
from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from typing import Any, Dict

from app.runtime.orchestrator_contracts import ResolutionAction, TaskStatus
from app.runtime.redactor import RuntimeRedactor
from app.runtime.memory.effective_scope import project_memory_context
from app.runtime.memory.execution_context import memory_execution_context
from app.runtime.prompt_projections import task_result_for_prompt


DEFAULT_SYNTHESIS_CONTEXT_MAX_CHARS = 120_000


class SynthesisContextError(ValueError):
    pass


class SynthesisContextBuilder:
    def __init__(self, *, max_chars: int = DEFAULT_SYNTHESIS_CONTEXT_MAX_CHARS) -> None:
        self._max_chars = max(1, int(max_chars))
        self._redactor = RuntimeRedactor()

    def build_partial(self, *, plan: Dict[str, Any], message: str,
                      deleted_artifact_ids: list[str] | None = None) -> Dict[str, Any]:
        """Build a final evidence package without applying a new plan iteration."""
        iteration_id = "runtime-finalization"
        projected = {**plan, "iterations": [*list(plan.get("iterations") or []), {
            "id": iteration_id, "synthesis_brief": {"user_question": plan.get("goal"),
                "purpose": "Give the supported partial answer", "answer_requirements": message},
        }]}
        context = self.build(plan=projected, iteration_id=iteration_id,
                             deleted_artifact_ids=deleted_artifact_ids)
        context["plan_outline"] = context["plan_outline"][:-1]
        # A failed plan has no verified agent report for contextual search
        # results. Do not let unrelated memory passages become an answer.
        context["memory_context"] = []
        return context

    def build(
        self, *, plan: Dict[str, Any], iteration_id: str,
        deleted_artifact_ids: list[str] | None = None,
        run_context: Dict[str, Any] | None = None,
        runtime_limitations: list[Dict[str, Any]] | None = None,
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
                for item in verified.get("limitations") or []:
                    if isinstance(item, dict):
                        limitations.append({"task_id": task_id, **self._redact(item)})
                references = self._verified_result_references(verified)
                expected_outputs = [
                    {"key": item.get("key"), "required": bool(item.get("required", True)),
                     "fulfillment": item.get("fulfillment")}
                    for item in task.get("expected_outputs", []) if isinstance(item, dict)
                ]
                reports.append(task_result_for_prompt({"task_id": task_id, "intent": self._redact(task.get("intent")),
                                "status": status, "completion": result.get("completion"),
                                "description": self._redact(result.get("description")),
                                "answer": self._redact(result.get("answer", result.get("description"))),
                                "structured_response": self._redact(result.get("structured_response", outputs)),
                                "outputs": self._redact(outputs), "needs": self._redact(result.get("needs", [])),
                                "output_states": self._redact(result.get("output_states", {})),
                                "expected_outputs": expected_outputs,
                                "verified_result_refs": references,
                                "diagnostics": self._redact(result.get("diagnostics", []))}))
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
        # Raw memory search passages are only a synthesis source for a
        # memory-only plan. Once agent work exists, its reports and sources
        # are the evidence package; passing the broad search history alongside
        # them can create unsupported links between unrelated entities.
        memory_context = []
        if not tasks and not limitations:
            for item in plan.get("memory_context") or []:
                if not isinstance(item, dict) or item.get("type") not in {"document_memory", "memory_recall", "planner_memory_result"}:
                    continue
                memory_context.append(project_memory_context(item, allowed_scope))
        context = {"user_question": plan.get("goal"), "synthesis_brief": self._redact(iteration["synthesis_brief"]), "plan_outline": [{"sequence": item.get("sequence"), "terminal": item.get("terminal")} for item in plan.get("iterations", [])], "resolution_decisions": self._redact([{key: item.get(key) for key in ("task_id", "action", "output_keys", "reason")} for item in resolutions if item.get("action") != ResolutionAction.CONTINUE_WITH_TASKS.value]), "completed_task_reports": reports, "limitations": limitations, "memory_context": self._redact(memory_context), "artifacts": deliverable_artifacts, "sources": self._dedupe(sources, "evidence_id")}
        context["scope_context"] = self._redact(plan.get("scope_context") or {})
        context["execution_context"] = memory_execution_context(
            list((plan.get("scope_context") or {}).get("keys") or []), revision=int((plan.get("scope_context") or {}).get("revision") or 0),
        )
        if run_context is not None:
            context["run_context"] = self._redact(run_context)
            unavailable = list(run_context.get("unavailable_material_refs") or [])
            omitted = list(run_context.get("omitted_material_refs") or [])
            if unavailable or omitted or run_context.get("evidence_coverage") in {"invalid_refs", "unavailable", "partial"}:
                context["limitations"].append({
                    "code": "selected_material_incomplete",
                    "message": "Some selected run material is unavailable or omitted from this synthesis input.",
                    "unavailable_material_refs": unavailable,
                    "omitted_material_refs": omitted,
                    "evidence_coverage": run_context.get("evidence_coverage"),
                })
        context["limitations"].extend(runtime_limitations or [])
        return self._compact_to_limit(context)

    def _compact_to_limit(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Build an exact-value partial projection and enumerate withheld fields."""
        if len(json.dumps(context, ensure_ascii=False, default=str)) <= self._max_chars:
            return context
        limitation = {"code": "synthesis_context_budget_exceeded",
                      "message": "Some exact synthesis material was withheld because it exceeded the configured context budget."}
        bounded: Dict[str, Any] = {
            key: deepcopy(context[key]) for key in (
                "user_question", "synthesis_brief", "plan_outline", "resolution_decisions",
                "scope_context", "execution_context", "execution_summary",
                "artifacts", "sources", "datastore", "evidence_preparation", "direct_answer_draft",
            ) if key in context
        }
        bounded["limitations"] = []
        bounded["completed_task_reports"] = []
        bounded["memory_context"] = []
        bounded["withheld_materials"] = []
        run_context_for_reserve = context.get("run_context") if isinstance(context.get("run_context"), dict) else {}
        expected_manifest_items = (
            len(context.get("completed_task_reports") or [])
            + len(run_context_for_reserve.get("evidence") or [])
            + len(run_context_for_reserve.get("conversation_materials") or [])
            + len(context.get("memory_context") or [])
        )
        reserve = len(json.dumps(limitation, ensure_ascii=False, default=str)) + 512 * max(1, expected_manifest_items)
        content_limit = max(1, self._max_chars - reserve)
        run_context = context.get("run_context")
        bounded_run: Dict[str, Any] | None = None
        if isinstance(run_context, dict):
            bounded_run = {key: deepcopy(run_context[key]) for key in (
                "original_request", "constraints", "answer_requirements", "resolved_references",
                "uncertainties", "evidence_catalog", "selected_material_refs", "available_material_refs",
                "unavailable_material_refs", "omitted_material_refs", "omitted_material_recovery",
                "evidence_coverage",
            ) if key in run_context}
            bounded_run["evidence"] = []
            bounded_run["conversation_materials"] = []
            bounded["run_context"] = bounded_run

        def fits() -> bool:
            return len(json.dumps(bounded, ensure_ascii=False, default=str)) <= content_limit

        def mark_withheld(item: Dict[str, Any]) -> None:
            if item.get("kind") == "task_result_field":
                previous = next((entry for entry in bounded["withheld_materials"]
                                 if entry.get("kind") == item["kind"]
                                 and entry.get("task_id") == item.get("task_id")), None)
                if previous is not None:
                    fields = previous.setdefault("fields", [])
                    if item.get("field") not in fields:
                        fields.append(item["field"])
                    return
                field = item.pop("field")
                item = {**item, "fields": [field]}
            bounded["withheld_materials"].append(item)

        report_fields = ("intent", "answer", "structured_response", "outputs", "needs", "diagnostics")
        for report in context.get("completed_task_reports", []):
            if not isinstance(report, dict):
                continue
            stub = {key: deepcopy(report[key]) for key in (
                "task_id", "status", "completion", "expected_outputs", "output_states", "verified_result_refs",
            ) if key in report}
            bounded["completed_task_reports"].append(stub)
            for key in report_fields:
                if key not in report:
                    continue
                stub[key] = deepcopy(report[key])
                if not fits():
                    stub.pop(key)
                    mark_withheld({
                        "kind": "task_result_field", "task_id": report.get("task_id"),
                        "field": key, "result_refs": deepcopy(report.get("verified_result_refs") or []),
                    })

        for item in context.get("limitations", []):
            bounded["limitations"].append(deepcopy(item))
            if not fits():
                bounded["limitations"].pop()
                serialized = json.dumps(item, ensure_ascii=False, default=str, sort_keys=True)
                mark_withheld({
                    "kind": "limitation", "reference": item.get("task_id") or item.get("code"),
                    "message_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                    "message_chars": len(str(item.get("message") or "")),
                })

        if isinstance(run_context, dict) and bounded_run is not None:
            for field, id_field in (("evidence", "id"), ("conversation_materials", "message_id")):
                for item in run_context.get(field, []):
                    if not isinstance(item, dict):
                        continue
                    bounded_run[field].append(deepcopy(item))
                    if not fits():
                        bounded_run[field].pop()
                        mark_withheld({"kind": field, "ref": item.get(id_field),
                                       "tool": item.get("tool")})

        for item in context.get("memory_context", []):
            bounded["memory_context"].append(deepcopy(item))
            if not fits():
                bounded["memory_context"].pop()
                mark_withheld({
                    "kind": "memory_context",
                    "scope": item.get("scope_slug") if isinstance(item, dict) else None,
                    "source_references": deepcopy(item.get("source_references") or [])
                    if isinstance(item, dict) else [],
                })

        for key in ("artifacts", "sources"):
            # These delivery/provenance fields are mandatory; if their exact
            # values do not fit, fail closed instead of dropping them.
            if key in context and bounded.get(key) != context[key]:
                raise SynthesisContextError(f"synthesis {key} exceed configured size")
        if bounded["withheld_materials"]:
            bounded["evidence_coverage"] = "partial"
            bounded["limitations"].append(limitation)
        final_size = len(json.dumps(bounded, ensure_ascii=False, default=str))
        if final_size > self._max_chars:
            raise SynthesisContextError(
                f"synthesis context cannot fit its explicit limitation manifest ({final_size}>{self._max_chars})")
        return bounded

    @staticmethod
    def _verified_result_references(verified: Dict[str, Any]) -> list[Dict[str, Any]]:
        """Return only result IDs paired with successful runtime-owned receipts."""
        references = []
        for receipt in verified.get("receipts") or []:
            if not isinstance(receipt, dict) or receipt.get("success") is not True or not receipt.get("result_id"):
                continue
            analysis = receipt.get("analysis") if isinstance(receipt.get("analysis"), dict) else {}
            observation = receipt.get("result_observation") if isinstance(receipt.get("result_observation"), dict) else {}
            references.append({
                "result_id": str(receipt["result_id"]),
                "operation": str(receipt.get("operation") or "unknown"),
                **({"observation": deepcopy(observation)} if observation else {}),
                **({"revision": observation["revision"]} if isinstance(observation.get("revision"), int)
                   else ({"revision": analysis["revision"]} if isinstance(analysis.get("revision"), int) else {})),
                **({"source_complete": receipt["source_complete"]} if isinstance(receipt.get("source_complete"), bool) else {}),
            })
        task_result_ref = verified.get("task_result_ref")
        if isinstance(task_result_ref, dict) and task_result_ref.get("status") == "available" and task_result_ref.get("result_id"):
            references.append({
                "result_id": str(task_result_ref["result_id"]),
                "operation": "runtime.task.result",
                "revision": task_result_ref.get("revision"),
                "path": task_result_ref.get("path"),
                "reader": task_result_ref.get("reader"),
                "reader_arguments": deepcopy(task_result_ref.get("reader_arguments") or {}),
            })
        return references

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
                **({"artifact": item["artifact"]} if isinstance(item.get("artifact"), dict) else {}),
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
            if item.get("artifact_id"):
                source["artifact_id"] = str(item["artifact_id"])
            if isinstance(item.get("artifact"), dict):
                source["artifact"] = self._redact(item["artifact"])
            if item.get("source_name") or item.get("title") or item.get("name"):
                source["source_name"] = item.get("source_name") or item.get("title") or item.get("name")
            for key in ("chunk_id", "page", "score", "representation_id", "start", "end"):
                if item.get(key) is not None:
                    source[key] = item[key]
            identity_parts = [str(source.get(key) or "") for key in
                              ("source_id", "chunk_id", "page", "start", "end", "representation_id")]
            if not any(identity_parts[1:]) and item.get("text"):
                identity_parts.append(hashlib.sha256(str(item["text"]).encode("utf-8")).hexdigest())
            source["evidence_id"] = ":".join(identity_parts)
            if item.get("text"):
                text = str(item["text"])
                source["excerpt"] = self._redact(text[:500])
                source["excerpt_truncated"] = len(text) > 500
                source["excerpt_length"] = len(text)
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
