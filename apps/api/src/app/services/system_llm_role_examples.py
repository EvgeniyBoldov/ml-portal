from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.system_llm_role import SystemLLMRoleType

ExamplesV2 = Dict[str, Any]

_EXAMPLES: Dict[SystemLLMRoleType, ExamplesV2] = {
    SystemLLMRoleType.PLANNER: {"input": {"goal": "Найти источник данных", "available_agents": [{"slug": "viewer"}]}, "outputs": {"apply_graph": {"action": "apply_graph", "tasks": [{"task_id": "discover", "executor": "viewer", "intent": "discover", "instructions": "Собрать источники"}, {"task_id": "assess_discovery", "kind": "planner", "intent": "Оценить найденные источники", "instructions": "Определить следующий участок графа", "depends_on": ["discover"]}]}}},
    SystemLLMRoleType.MEMORY: {"input": {"request": "Заявка для Нема", "facts": [{"index": 0}], "projects": [{"index": 0, "aliases": ["Нема"]}]}, "outputs": {"default": {"fact_indexes": [0], "project_indexes": [0], "ambiguities": []}}},
    SystemLLMRoleType.FACT_EXTRACTOR: {"input": {"user_message": "Я сетевой инженер", "evidence": [{"source_id": "user_message", "source_type": "user_message", "source_ref": "request", "text": "Я сетевой инженер"}], "known_facts": []}, "outputs": {"default": {"facts": [{"scope": "user", "kind": "fact", "subject": "user.role", "value": "network engineer", "confidence": 0.9, "aliases": [], "project_aliases": [], "evidence_source_ids": ["user_message"]}]}}},
    SystemLLMRoleType.FACT_COMPACTOR: {"input": {"candidates": [{"index": 0, "scope": "tenant", "subject": "standard", "value": "ITIL"}], "current_facts": []}, "outputs": {"default": {"facts": [{"scope": "tenant", "subject": "standard", "value": "ITIL", "action": "merge", "source_candidate_indexes": [0], "target_current_indexes": []}]}}},
}


def get_role_examples(role: SystemLLMRoleType | str) -> Optional[ExamplesV2]:
    role_type = role if isinstance(role, SystemLLMRoleType) else SystemLLMRoleType(str(role))
    return _EXAMPLES.get(role_type)
