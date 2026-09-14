from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.system_llm_role import SystemLLMRoleType

ExamplesV2 = Dict[str, Any]

_EXAMPLES: Dict[SystemLLMRoleType, ExamplesV2] = {
    SystemLLMRoleType.TURN_PREFLIGHT: {"input": {"user_request": "Что означает СРК?", "mechanical_lookup": {"glossary": [{"term": "СРК"}]}}, "outputs": {"default": {"route": "recall", "memory_request": {"direction": "definition", "query": "СРК"}}}},
    SystemLLMRoleType.PLANNER: {
        "input": {
            "goal": "Найти источник данных",
            "available_agents": [{"slug": "viewer"}],
        },
        "outputs": {
            "default": {
                "kind": "proposal",
                "proposal": {
                    "tasks": [{
                        "task_id": "discover",
                        "executor": "viewer",
                        "intent": "discover",
                        "instructions": "Собрать источники",
                        "expected_outputs": [{
                            "key": "sources",
                            "description": "Найденные источники",
                        }],
                    }],
                    "terminal": "planner",
                    "bindings": [],
                    "resolutions": [],
                },
            },
        },
    },
    SystemLLMRoleType.MEMORY: {"input": {"request": "Заявка для Нема", "facts": [{"index": 0}], "projects": [{"index": 0, "aliases": ["Нема"]}]}, "outputs": {"default": {"fact_indexes": [0], "project_indexes": [0], "glossary_indexes": [], "ambiguities": [], "intent": "informational"}}},
    SystemLLMRoleType.FACT_EXTRACTOR: {"input": {"user_message": "Я сетевой инженер", "evidence": [{"source_id": "user_message", "source_type": "user_message", "source_ref": "request", "text": "Я сетевой инженер"}], "known_facts": []}, "outputs": {"default": {"facts": [{"scope": "user", "kind": "fact", "subject": "user.role", "value": "network engineer", "confidence": 0.9, "aliases": [], "project_aliases": [], "evidence_source_ids": ["user_message"]}]}}},
    SystemLLMRoleType.FACT_COMPACTOR: {"input": {"candidates": [{"index": 0, "scope": "tenant", "subject": "standard", "value": "ITIL"}], "current_facts": []}, "outputs": {"default": {"facts": [{"scope": "tenant", "subject": "standard", "value": "ITIL", "action": "merge", "source_candidate_indexes": [0], "target_current_indexes": []}]}}},
    SystemLLMRoleType.DOCUMENT_MEMORY_EXTRACTOR: {"input": {"document": {"title": "Switch changes"}, "sections": [{"id": "section-1", "text": "Before a VLAN change, create a backup."}], "projects": [{"key": "network", "name": "Network"}]}, "outputs": {"default": {"items": [{"item_type": "procedure", "subject": "network.change_vlan", "content": {"goal": "Change VLAN", "applicability_conditions": [], "required_approvals": [], "prechecks": ["Create a backup"], "steps": [{"instruction": "Change VLAN", "expected_result": "VLAN is applied", "confirmation_required": True}], "verification": ["Verify connectivity"], "rollback": {"mode": "steps", "steps": ["Restore backup"], "reason": None}, "exceptions": []}, "project_key": "network", "project_confidence": 0.95, "evidence_section_ids": ["section-1"], "aliases": [], "term_kind": None}]}}},
    SystemLLMRoleType.MEMORY_EVALUATOR: {"input": {"memory_item": {"subject": "network.change_vlan", "content": {"steps": ["backup"]}}, "evidence": [{"text": "Create a backup before changing VLAN."}]}, "outputs": {"default": {"outcome": "confirmed", "reason": "The evidence states the same prerequisite.", "evidence_hit_indexes": [0]}}},
}


def get_role_examples(role: SystemLLMRoleType | str) -> Optional[ExamplesV2]:
    role_type = role if isinstance(role, SystemLLMRoleType) else SystemLLMRoleType(str(role))
    return _EXAMPLES.get(role_type)
