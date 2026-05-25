from __future__ import annotations

from typing import Any, Dict, List, Optional


AGENT_VERSION_PROMPT_FIELDS = frozenset({
    "identity", "mission", "scope", "rules",
    "tool_use_rules", "output_format", "examples",
})
AGENT_VERSION_EXEC_FIELDS = frozenset({
    "model", "temperature",
})
AGENT_VERSION_SAFETY_FIELDS = frozenset({
    "never_do", "allowed_ops",
})
AGENT_VERSION_ROUTING_FIELDS = frozenset({"tags"})
AGENT_VERSION_ALL_FIELDS = (
    AGENT_VERSION_PROMPT_FIELDS
    | AGENT_VERSION_EXEC_FIELDS
    | AGENT_VERSION_SAFETY_FIELDS
    | AGENT_VERSION_ROUTING_FIELDS
)

PLATFORM_GATE_FIELDS = frozenset({
    "require_confirmation_for_write", "require_confirmation_for_destructive",
    "forbid_destructive", "forbid_write_in_prod", "require_backup_before_write",
})
PLATFORM_POLICY_FIELDS = frozenset({"policies_text"})


def _field(
    key: str,
    label: str,
    field_path: str,
    *,
    field_type: str = "text",
    editable: bool = True,
    options: Optional[List[str]] = None,
    help_text: Optional[str] = None,
    source_key: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "field_path": field_path,
        "field_type": field_type,
        "editable": editable,
        "options": options or [],
        "help_text": help_text,
        "source_key": source_key,
    }


def _section(title: str, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"title": title, "fields": fields}


def _blueprint(
    key: str,
    title: str,
    entity_type: str,
    sections: List[Dict[str, Any]],
    *,
    description: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "description": description,
        "sections": sections,
}


def _limit_fields(prefix: str = "limits") -> List[Dict[str, Any]]:
    return [
        _field("llm_input_tokens_max", "LLM input tokens", f"{prefix}.llm_input_tokens_max", field_type="integer", source_key="limits.llm_input_tokens_max"),
        _field("llm_output_tokens_max", "LLM output tokens", f"{prefix}.llm_output_tokens_max", field_type="integer", source_key="limits.llm_output_tokens_max"),
        _field("llm_context_window_max", "LLM context window", f"{prefix}.llm_context_window_max", field_type="integer", source_key="limits.llm_context_window_max"),
        _field("runtime_steps_max", "Runtime steps", f"{prefix}.runtime_steps_max", field_type="integer", source_key="limits.runtime_steps_max"),
        _field("runtime_tool_calls_max", "Runtime tool calls", f"{prefix}.runtime_tool_calls_max", field_type="integer", source_key="limits.runtime_tool_calls_max"),
        _field("runtime_retries_max", "Runtime retries", f"{prefix}.runtime_retries_max", field_type="integer", source_key="limits.runtime_retries_max"),
        _field("runtime_wall_time_ms_max", "Runtime wall time (ms)", f"{prefix}.runtime_wall_time_ms_max", field_type="integer", source_key="limits.runtime_wall_time_ms_max"),
        _field("runtime_tokens_total_max", "Runtime total tokens", f"{prefix}.runtime_tokens_total_max", field_type="integer", source_key="limits.runtime_tokens_total_max"),
    ]


SANDBOX_BLUEPRINTS: List[Dict[str, Any]] = [
    _blueprint(
        "agent",
        "Агент",
        "agent_version",
        [
            _section(
                "Основное",
                [
                    _field("version", "Версия", "version", field_type="integer", editable=False),
                    _field("status", "Статус", "status", field_type="select", editable=False),
                    _field("created_at", "Создан", "created_at", field_type="text", editable=False),
                    _field("updated_at", "Обновлён", "updated_at", field_type="text", editable=False),
                ],
            ),
            _section(
                "Prompt",
                [
                    _field("identity", "Identity", "identity", field_type="text"),
                    _field("mission", "Mission", "mission", field_type="text"),
                    _field("scope", "Scope", "scope", field_type="text"),
                    _field("rules", "Rules", "rules", field_type="text"),
                    _field("tool_use_rules", "Tool Use Rules", "tool_use_rules", field_type="text"),
                    _field("output_format", "Output Format", "output_format", field_type="text"),
                    _field("examples", "Examples", "examples", field_type="json"),
                ],
            ),
            _section(
                "Execution",
                [
                    _field("model", "Model", "model", field_type="text"),
                    _field("temperature", "Temperature", "temperature", field_type="float"),
                ],
            ),
            _section("Limits", _limit_fields("limits")),
            _section(
                "Safety",
                [
                    _field("never_do", "Never do", "never_do", field_type="text"),
                    _field("allowed_ops", "Allowed ops", "allowed_ops", field_type="text"),
                ],
            ),
            _section("Tags", [_field("tags", "Tags", "tags", field_type="tags")]),
            _section(
                "Meta",
                [
                    _field("notes", "Notes", "notes", field_type="text"),
                    _field("parent_version_id", "Parent version", "parent_version_id", field_type="text", editable=False),
                ],
            ),
        ],
    ),
    _blueprint(
        "tool",
        "Инструмент",
        "tool_release",
        [
            _section(
                "Основное",
                [
                    _field("version", "Версия", "version", field_type="integer", editable=False),
                    _field("status", "Статус", "status", field_type="select", editable=False),
                    _field("created_at", "Создан", "created_at", field_type="text", editable=False),
                    _field("updated_at", "Обновлён", "updated_at", field_type="text", editable=False),
                    _field("parent_release_id", "Parent release", "parent_release_id", field_type="text", editable=False),
                ],
            ),
            _section(
                "Backend",
                [
                    _field("backend_release_id", "Backend release", "backend_release_id", field_type="text", editable=False),
                    _field("meta_hash", "Meta hash", "meta_hash", field_type="text", editable=False),
                    _field("expected_schema_hash", "Expected schema hash", "expected_schema_hash", field_type="text", editable=False),
                    _field("backend_version", "Backend version", "backend_release.version", field_type="text", editable=False, source_key="backend_release.version"),
                    _field("backend_description", "Backend description", "backend_release.description", field_type="text", editable=False, source_key="backend_release.description"),
                    _field("backend_method_name", "Method", "backend_release.method_name", field_type="text", editable=False, source_key="backend_release.method_name"),
                    _field("backend_deprecated", "Deprecated", "backend_release.deprecated", field_type="boolean", editable=False, source_key="backend_release.deprecated"),
                    _field("backend_schema_hash", "Schema hash", "backend_release.schema_hash", field_type="text", editable=False, source_key="backend_release.schema_hash"),
                    _field("backend_worker_build_id", "Build id", "backend_release.worker_build_id", field_type="text", editable=False, source_key="backend_release.worker_build_id"),
                    _field("backend_last_seen_at", "Last seen", "backend_release.last_seen_at", field_type="text", editable=False, source_key="backend_release.last_seen_at"),
                ],
            ),
            _section(
                "Схемы",
                [
                    _field("input_schema", "Input schema", "backend_release.input_schema", field_type="json", editable=False, source_key="backend_release.input_schema"),
                    _field("output_schema", "Output schema", "backend_release.output_schema", field_type="json", editable=False, source_key="backend_release.output_schema"),
                ],
            ),
        ],
    ),
    _blueprint(
        "discovered_tool",
        "Инструмент",
        "discovered_tool",
        [
            _section(
                "Основное",
                [
                    _field("published", "Опубликован", "published", field_type="boolean"),
                    _field("tool_release_id", "Релиз инструмента", "tool_release_id", field_type="select", source_key="current_version_id"),
                    _field("source", "Источник", "source", field_type="text", editable=False),
                    _field("slug", "Slug", "slug", field_type="text", editable=False),
                    _field("name", "Название", "name", field_type="text"),
                    _field("domains", "Домены", "domains", field_type="tags"),
                ],
            ),
            _section(
                "Семантика",
                [
                    _field("description", "Description", "description", field_type="text"),
                    _field("side_effects", "Side effects", "side_effects", field_type="boolean"),
                    _field("risk_level", "Risk level", "risk_level", field_type="select", options=["safe", "write", "destructive"]),
                    _field("idempotent", "Idempotent", "idempotent", field_type="boolean"),
                    _field("requires_confirmation", "Requires confirmation", "requires_confirmation", field_type="boolean"),
                    _field("credential_scope", "Credential scope", "credential_scope", field_type="select", options=["auto", "user", "platform"]),
                    _field("examples", "Examples", "examples", field_type="json"),
                    _field("input_schema", "Input schema", "input_schema", field_type="json", editable=False),
                    _field("output_schema", "Output schema", "output_schema", field_type="json", editable=False),
                ],
            ),
        ],
    ),
    _blueprint(
        "router",
        "Оркестратор",
        "orchestration",
        [
            _section(
                "Основное",
                [
                    _field("identity", "Identity", "identity", field_type="text"),
                    _field("mission", "Mission", "mission", field_type="text"),
                    _field("rules", "Rules", "rules", field_type="text"),
                    _field("safety", "Safety", "safety", field_type="text"),
                    _field("output_requirements", "Output requirements", "output_requirements", field_type="text"),
                    _field("examples", "Examples", "examples", field_type="json"),
                ],
            ),
            _section(
                "Execution",
                [
                    _field("model", "Model", "model", field_type="text"),
                    _field("temperature", "Temperature", "temperature", field_type="float"),
                    _field("max_tokens", "Max tokens", "max_tokens", field_type="integer"),
                    _field("timeout_s", "Timeout (s)", "timeout_s", field_type="integer"),
                    _field("max_retries", "Max retries", "max_retries", field_type="integer"),
                    _field("retry_backoff", "Retry backoff", "retry_backoff", field_type="text"),
                ],
            ),
            _section("Limits", _limit_fields("limits")),
        ],
    ),
    _blueprint(
        "tenant",
        "Тенант",
        "orchestration",
        [
            _section(
                "Агент",
                [
                    _field("agent_version_id", "Agent version", "agent.version_id", field_type="select", source_key="agent_version_id"),
                ],
            ),
            _section(
                "Тенант",
                [
                    _field("agent_slug", "Agent slug", "agent.slug", field_type="select", source_key="agent_slug"),
                ],
            ),
        ],
    ),
    _blueprint(
        "platform",
        "Платформа",
        "orchestration",
        [
            _section(
                "Policy",
                [
                    _field("policies_text", "Policies", "platform.policies_text", field_type="text", source_key="policies_text"),
                ],
            ),
            _section(
                "Gates",
                [
                    _field("require_confirmation_for_write", "Confirmation for write", "platform.require_confirmation_for_write", field_type="boolean", source_key="require_confirmation_for_write"),
                    _field("require_confirmation_for_destructive", "Confirmation for destructive", "platform.require_confirmation_for_destructive", field_type="boolean", source_key="require_confirmation_for_destructive"),
                    _field("forbid_destructive", "Forbid destructive", "platform.forbid_destructive", field_type="boolean", source_key="forbid_destructive"),
                    _field("forbid_write_in_prod", "Forbid write in prod", "platform.forbid_write_in_prod", field_type="boolean", source_key="forbid_write_in_prod"),
                    _field("require_backup_before_write", "Require backup before write", "platform.require_backup_before_write", field_type="boolean", source_key="require_backup_before_write"),
                ],
            ),
            _section("Limits", _limit_fields("platform_limits")),
        ],
    ),
]
