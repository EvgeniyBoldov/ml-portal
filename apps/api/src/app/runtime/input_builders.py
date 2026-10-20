"""Runtime input builders for planner/synthesizer surfaces."""
from __future__ import annotations
from typing import Any, Dict, List
from copy import deepcopy

from app.runtime.memory.execution_context import memory_execution_context
from app.runtime.memory.effective_scope import project_memory_context
from app.runtime.datastore_context import build_datastore, task_files


MAX_AGENT_DESCRIPTION_CHARS = 280
MAX_PLANNER_MEMORY_PASSAGE_CHARS = 3_000


def compact_memory_search_result(result: Any) -> dict[str, Any]:
    """Project a search receipt to passages and source labels once."""
    if not isinstance(result, dict):
        return {}
    if isinstance(result.get("groups"), list):
        return {**deepcopy(result), "group_count": len(result["groups"]),
                "success": result.get("success", True),
                "partial": result.get("partial", any(not group.get("success", True) for group in result["groups"]))}
    items = result.get("items") if isinstance(result.get("items"), list) else []
    compact_items = []
    for item in items[:12]:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        refs = item.get("source_references") or metadata.get("source_refs") or []
        compact_refs = []
        seen_refs: set[tuple[str, str]] = set()
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            document_id = str(ref.get("document_id") or "")
            title = str(ref.get("document_title") or ref.get("filename") or "")
            key = (document_id, title)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            compact_refs.append({"document_id": document_id, "document_title": title})
        compact_items.append({
            "kind": item.get("kind"),
            "subject": item.get("subject") or metadata.get("document_title") or metadata.get("filename"),
            "text": str(item.get("text") or "")[:MAX_PLANNER_MEMORY_PASSAGE_CHARS],
            "source_id": metadata.get("source_id"),
            "source_references": compact_refs,
        })
    memory_context = result.get("memory_context")
    compact_context = {
        key: memory_context.get(key)
        for key in ("type", "rag_required", "tool_required", "clarification_required", "source_references")
        if isinstance(memory_context, dict) and key in memory_context
    }
    return {
        "success": result.get("success", True),
        "backend": result.get("backend"),
        "count": result.get("count", len(compact_items)),
        "items": compact_items,
        "memory_context": compact_context,
    }


def compact_memory_tool_records(records: Any) -> list[dict[str, Any]]:
    compacted = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        compacted.append({
            **({"evidence_id": record["evidence_id"]} if record.get("evidence_id") else {}),
            "tool": record.get("tool"),
            "arguments": record.get("arguments"),
            "result": (compact_memory_search_result(record.get("result")) if record.get("tool") == "memory.search" else deepcopy(record.get("result") or {})),
        })
    return compacted


def _planner_search_summaries(records: Any) -> list[dict[str, Any]]:
    """Expose search bookkeeping without repeating passages from memory_context."""
    summaries = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        result = record.get("result") if isinstance(record.get("result"), dict) else {}
        summaries.append({
            "tool": record.get("tool"),
            "arguments": record.get("arguments"),
            "success": result.get("success", True),
            "count": result.get("count"),
        })
    return summaries


def _planner_memory_projection(entries: Any, scope_keys: list[str]) -> list[dict[str, Any]]:
    """Keep evidence useful for planning without serializing nested search copies."""
    projected: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict) or entry.get("type") != "planner_memory_result":
            projected.append(entry)
            continue

        scoped = project_memory_context(entry, scope_keys)
        record = scoped.get("result") if isinstance(scoped.get("result"), dict) else {}
        compact_result = compact_memory_search_result(record)
        projected.append({
            "type": "planner_memory_result",
            "query_key": scoped.get("query_key"),
            "arguments": scoped.get("arguments"),
            "result": {
                **compact_result,
            },
        })
    return projected


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
                "task_contracts": [
                    {
                        "contract_id": contract.get("contract_id"),
                        "version": contract.get("version"),
                        "description": contract.get("description"),
                        # Published data schemas guide LLMs without rejecting their inputs.
                        "input_schema": contract.get("input_schema"),
                        "response_spec": contract.get("response_spec"),
                        "output_hints": contract.get("expected_outputs", []),
                    }
                    for contract in item.get("task_contracts") or [] if isinstance(contract, dict)
                ],
                "supports_dynamic_contracts": bool(item.get("supports_dynamic_contracts", True)),
                "requires_fresh_retrieval": bool(item.get("requires_fresh_retrieval", False)),
            })
        payload = {
            "goal": context.goal,
            "trigger": context.trigger,
            "execution_ledger": context.execution_ledger,
            "datastore": build_datastore(
                files=[*context.available_artifacts, *task_files(
                    item.get("result") for item in context.execution_ledger.get("tasks", [])
                    if isinstance(item, dict))],
                results=context.available_results, results_status=context.result_catalog_status,
                deleted_artifact_ids=context.deleted_artifact_ids),
            "memory_context": _planner_memory_projection(
                context.memory_context, list(context.scope_context.get("keys") or []),
            ),
            "scope_context": context.scope_context,
            "execution_context": memory_execution_context(context.scope_context.get("keys") or [],
                revision=int(context.scope_context.get("revision") or 0)),
            "planner_search_results": _planner_search_summaries(context.planner_search_results),
            "task_brief": context.task_brief,
            "available_agents": agents,
            "iteration_contract": {
                "protocol_version": 2,
                "data_schemas_are_advisory": True,
                "only_required_artifacts_are_enforced": True,
                "bindings_allow_prior_completed_producers": True,
                "tasks_are_agents_only": True,
                "terminal": ["planner", "synthesis"],
                "synthesis_requires_brief": True,
                "partial_results_require_resolution": True,
                "bindings_require_pending_needs": True,
                "empty_needs_require_empty_bindings": True,
                "bound_consumer_inputs_must_be_omitted": True,
            },
        }
        return payload

    @staticmethod
    def _trim_text(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit]

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
