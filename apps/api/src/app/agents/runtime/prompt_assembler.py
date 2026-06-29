"""Prompt assembler for runtime-facing agent prompts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from app.agents.protocol import build_operations_prompt
from app.agents.runtime.prompt_contract import build_prompt_input_schema, build_prompt_operation_description
from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer
from app.agents.runtime.capability_card_builder import CapabilityCardBuilder
from app.agents.runtime.policy import PolicyLimits

if TYPE_CHECKING:
    from app.agents.contracts import ResolvedDataInstance, ResolvedOperation
    from app.agents.execution_preflight import ExecutionRequest


@dataclass(slots=True)
class PromptAssembly:
    base_prompt: str
    capability_prompt: str = ""
    collection_prompt: str = ""
    operations_prompt: str = ""
    system_prompt: str = ""
    sections: List[str] = field(default_factory=list)


class CollectionPromptRenderer:
    @staticmethod
    def render(payload: Dict[str, Any]) -> str:
        name = _text(payload.get("name")) or _text(payload.get("slug")) or "collection"
        slug = _text(payload.get("slug"))
        collection_type = (
            _text(payload.get("collection_type"))
            or _text(payload.get("domain"))
            or _text(payload.get("instance_kind"))
            or "data"
        )
        description = _text(payload.get("data_description")) or _text(payload.get("description"))
        purpose = _text(payload.get("usage_purpose"))
        entity_type = _text(payload.get("entity_type"))
        usage_rules = _text(payload.get("usage_rules"))

        lines: List[str] = [f"### {name}"]
        if slug:
            lines.append(f"- Slug: `{slug}`")
        if collection_type:
            lines.append(f"- Type: {collection_type}")
        if entity_type:
            lines.append(f"- Entity type: {entity_type}")
        if description:
            lines.append(f"- Description: {description}")
        if purpose:
            lines.append(f"- Purpose: {purpose}")
        if usage_rules:
            lines.append(f"- Usage rules: {usage_rules}")
        return "\n".join(lines)


class OperationPromptRenderer:
    MAX_DESCRIPTION_CHARS = 240

    @staticmethod
    def render_schema(op: "ResolvedOperation") -> Dict[str, Any]:
        prompt_meta = OperationPromptRenderer._build_prompt_metadata(op)
        description = build_prompt_operation_description(op, summary=getattr(op, "published", None), max_chars=OperationPromptRenderer.MAX_DESCRIPTION_CHARS)
        return {
            "type": "function",
            "function": {
                "name": op.operation_slug,
                "description": description,
                "parameters": _compact_json_schema(build_prompt_input_schema(op)),
            },
        }

    @staticmethod
    def _build_prompt_metadata(op: "ResolvedOperation") -> Dict[str, Any]:
        published = getattr(op, "published", None)
        canonical_name = _text(getattr(published, "canonical_name", None)) or op.operation
        collection_slug = (
            _text(getattr(published, "collection_slug", None))
            or _text(getattr(op, "collection_slug", None))
            or (_text(getattr(op, "data_instance_slug", None)) if op.scope == "collection" else "")
        )
        collection_type = _text(getattr(published, "collection_type", None))
        result_kind = _text(getattr(published, "result_kind", None)) or _text(getattr(op, "result_kind", None))
        title = _text(getattr(published, "title", None)) or _text(getattr(op, "name", None))
        description = _text(getattr(published, "description", None)) or _text(getattr(op, "description", None))
        return {
            "canonical_name": canonical_name,
            "scope_kind": op.scope,
            "collection_slug": collection_slug or None,
            "collection_type": collection_type or None,
            "result_kind": result_kind or None,
            "title": title or None,
            "description": description or None,
        }

class PromptAssembler:
    def __init__(
        self,
        agent_renderer: Optional[AgentPromptRenderer] = None,
        collection_renderer: Optional[CollectionPromptRenderer] = None,
        operation_renderer: Optional[OperationPromptRenderer] = None,
        capability_card_builder: Optional[CapabilityCardBuilder] = None,
    ) -> None:
        self.agent_renderer = agent_renderer or AgentPromptRenderer()
        self.collection_renderer = collection_renderer or CollectionPromptRenderer()
        self.operation_renderer = operation_renderer or OperationPromptRenderer()
        self.capability_card_builder = capability_card_builder or CapabilityCardBuilder()

    def assemble(
        self,
        exec_request: "ExecutionRequest",
        *,
        system_prompt_override: Optional[str] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        operation_schemas: Optional[List[Dict[str, Any]]] = None,
        resolved_operations: Optional[Sequence["ResolvedOperation"]] = None,
        policy_limits: Optional[PolicyLimits] = None,
        platform_config: Optional[Dict[str, Any]] = None,
    ) -> PromptAssembly:
        resolved_policy_limits = policy_limits or PolicyLimits.from_policy(
            exec_request.policy_data,
            exec_request.limit_data,
        )
        prompt_labels = self._resolve_prompt_labels(platform_config=platform_config, sandbox_overrides=sandbox_overrides)
        prompt_budgets = self._resolve_prompt_budgets(platform_config=platform_config, sandbox_overrides=sandbox_overrides)
        base_prompt = self.agent_renderer.render_base_prompt(
            exec_request,
            system_prompt_override=system_prompt_override,
            sandbox_overrides=sandbox_overrides,
        )
        capability_prompt = ""
        if resolved_operations is not None:
            capability_prompt = self.capability_card_builder.build(
                exec_request=exec_request,
                resolved_operations=resolved_operations,
                prompt_labels=prompt_labels,
                prompt_budgets=prompt_budgets,
            ).combined
        collection_prompt = self.assemble_collection_prompt(exec_request.resolved_data_instances)
        constraints_prompt = self.assemble_constraints_prompt(
            exec_request=exec_request,
            policy_limits=resolved_policy_limits,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
            prompt_labels=prompt_labels,
            prompt_budgets=prompt_budgets,
        )
        if operation_schemas is None and resolved_operations is not None:
            operation_schemas = self.assemble_operation_schemas(resolved_operations)
        operations_rules_override = self._resolve_operations_rules_override(
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
        )
        operations_prompt = (
            build_operations_prompt(
                operation_schemas,
                mandatory_rules_text=operations_rules_override,
                prompt_labels=prompt_labels,
                prompt_budgets=prompt_budgets,
            )
            if operation_schemas
            else ""
        )
        sections = [
            section
            for section in [
                base_prompt,
                capability_prompt,
                collection_prompt if not capability_prompt else "",
                constraints_prompt,
                operations_prompt,
            ]
            if section
        ]
        return PromptAssembly(
            base_prompt=base_prompt,
            capability_prompt=capability_prompt,
            collection_prompt=collection_prompt,
            operations_prompt=operations_prompt,
            system_prompt="\n\n".join(sections),
            sections=sections,
        )

    def assemble_collection_prompt(
        self,
        resolved_data_instances: Sequence["ResolvedDataInstance"],
    ) -> str:
        if not resolved_data_instances:
            return ""
        blocks = [
            self.collection_renderer.render(item.model_dump())
            for item in resolved_data_instances
        ]
        blocks = [block for block in blocks if block]
        if not blocks:
            return ""
        return "## Доступные коллекции\n\n" + "\n\n".join(blocks)

    def assemble_constraints_prompt(
        self,
        *,
        exec_request: "ExecutionRequest",
        policy_limits: PolicyLimits,
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        prompt_labels: Optional[Dict[str, Any]] = None,
        prompt_budgets: Optional[Dict[str, Any]] = None,
    ) -> str:
        labels = prompt_labels if isinstance(prompt_labels, dict) else {}
        budgets = prompt_budgets if isinstance(prompt_budgets, dict) else {}
        blocks: List[str] = []
        blocks.append(
            f"### {self._label(labels, 'runtime_limits_title', 'Ограничения')}\n"
            + "\n".join([
                f"- {self._label(labels, 'max_steps_label', 'Макс. шагов')}: {policy_limits.max_steps}",
                f"- {self._label(labels, 'max_tool_calls_label', 'Макс. вызовов операций')}: {policy_limits.max_tool_calls_total}",
                f"- {self._label(labels, 'max_wall_time_label', 'Макс. время выполнения (ms)')}: {policy_limits.max_wall_time_ms}",
                f"- {self._label(labels, 'tool_timeout_label', 'Таймаут операции (ms)')}: {policy_limits.tool_timeout_ms}",
                f"- {self._label(labels, 'max_retries_label', 'Макс. повторов')}: {policy_limits.max_retries}",
                f"- {self._label(labels, 'streaming_label', 'Стриминг')}: {policy_limits.streaming_enabled}",
                f"- {self._label(labels, 'citations_label', 'Требуются цитаты')}: {policy_limits.citations_required}",
                f"- {self._label(labels, 'parallel_calls_label', 'Параллельные вызовы')}: {policy_limits.allow_parallel_tool_calls}",
            ])
        )
        if exec_request.policy_data:
            blocks.append(f"### {self._label(labels, 'policy_version_title', 'Версия политики')}\n{_compact_json(exec_request.policy_data)}")
        if exec_request.limit_data:
            blocks.append(f"### {self._label(labels, 'limit_version_title', 'Версия лимитов')}\n{_compact_json(exec_request.limit_data)}")

        platform_lines: List[str] = []
        if isinstance(platform_config, dict):
            policies_text = _text(platform_config.get("policies_text"))
            if policies_text:
                max_policy_chars = self._budget(budgets, "policies_text_max_chars", 1200)
                if len(policies_text) > max_policy_chars:
                    policies_text = policies_text[:max_policy_chars].rstrip()
                platform_lines.append(f"- {self._label(labels, 'policies_label', 'Политики')}: {policies_text}")
        if platform_lines:
            blocks.append(f"{self._label(labels, 'platform_constraints_title', 'Ограничения платформы')}\n" + "\n".join(platform_lines))

        include_sandbox_notes = bool(
            isinstance(sandbox_overrides, dict)
            and sandbox_overrides.get("include_sandbox_notes_in_prompt") is True
        )
        sandbox_lines = self._extract_sandbox_notes(sandbox_overrides) if include_sandbox_notes else []
        if sandbox_lines:
            blocks.append(f"{self._label(labels, 'sandbox_notes_title', 'Заметки sandbox')}\n" + "\n".join(f"- {line}" for line in sandbox_lines))

        if len(blocks) == 1 and not platform_lines and not sandbox_lines and not exec_request.policy_data and not exec_request.limit_data:
            return ""
        return f"## {self._label(labels, 'runtime_constraints_title', 'Ограничения рантайма')}\n\n" + "\n\n".join(blocks)

    def assemble_operation_schemas(
        self,
        resolved_operations: Sequence["ResolvedOperation"],
    ) -> List[Dict[str, Any]]:
        if not resolved_operations:
            return []
        return [self.operation_renderer.render_schema(op) for op in resolved_operations]

    @staticmethod
    def _extract_sandbox_notes(sandbox_overrides: Optional[Dict[str, Any]]) -> List[str]:
        if not sandbox_overrides:
            return []
        notes: List[str] = []
        if sandbox_overrides.get("prompt"):
            notes.append("System prompt overridden in sandbox.")
        orch = sandbox_overrides.get("orchestration")
        if isinstance(orch, dict) and orch:
            notes.append(f"Orchestration overrides: {', '.join(sorted(orch.keys()))}")
        platform = sandbox_overrides.get("platform")
        if isinstance(platform, dict) and platform:
            notes.append(f"Platform overrides: {', '.join(sorted(platform.keys()))}")
        return notes

    @staticmethod
    def _resolve_operations_rules_override(
        *,
        platform_config: Optional[Dict[str, Any]],
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if isinstance(sandbox_overrides, dict):
            value = sandbox_overrides.get("operations_rules_text")
            if isinstance(value, str) and value.strip():
                return value.strip()
        if isinstance(platform_config, dict):
            value = platform_config.get("operations_rules_text")
            if isinstance(value, str) and value.strip():
                return value.strip()
            # Fallback to OrchestrationSettings.tool_use_guard
            value = platform_config.get("tool_use_guard")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _resolve_prompt_labels(
        *,
        platform_config: Optional[Dict[str, Any]],
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        labels: Dict[str, Any] = {}
        if isinstance(platform_config, dict) and isinstance(platform_config.get("prompt_labels"), dict):
            labels.update(platform_config["prompt_labels"])
        if isinstance(sandbox_overrides, dict) and isinstance(sandbox_overrides.get("prompt_labels"), dict):
            labels.update(sandbox_overrides["prompt_labels"])
        return labels

    @staticmethod
    def _resolve_prompt_budgets(
        *,
        platform_config: Optional[Dict[str, Any]],
        sandbox_overrides: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        budgets: Dict[str, Any] = {}
        if isinstance(platform_config, dict) and isinstance(platform_config.get("prompt_budgets"), dict):
            budgets.update(platform_config["prompt_budgets"])
        if isinstance(sandbox_overrides, dict) and isinstance(sandbox_overrides.get("prompt_budgets"), dict):
            budgets.update(sandbox_overrides["prompt_budgets"])
        return budgets

    @staticmethod
    def _label(labels: Dict[str, Any], key: str, default: str) -> str:
        value = labels.get(key)
        return str(value).strip() if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _budget(budgets: Dict[str, Any], key: str, default: int) -> int:
        def _coerce(value: Any) -> Optional[int]:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        direct = _coerce(budgets.get(key))
        if direct is not None:
            return direct
        for section in ("prompt_assembler", "constraints", "policy"):
            section_value = budgets.get(section)
            if isinstance(section_value, dict):
                nested = _coerce(section_value.get(key))
                if nested is not None:
                    return nested
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return _text(value)


def _compact_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only prompt-relevant JSON schema parts to reduce token overhead."""
    if not isinstance(schema, dict) or not schema:
        return {}

    compact: Dict[str, Any] = {}
    root_type = schema.get("type")
    if isinstance(root_type, str):
        compact["type"] = root_type
    elif "properties" in schema:
        compact["type"] = "object"

    properties = schema.get("properties")
    if isinstance(properties, dict) and properties:
        compact_props: Dict[str, Any] = {}
        for idx, (name, field) in enumerate(properties.items()):
            if idx >= 12:
                break
            if not isinstance(field, dict):
                continue
            prop: Dict[str, Any] = {}
            field_type = field.get("type")
            if isinstance(field_type, str):
                prop["type"] = field_type
            if "enum" in field and isinstance(field.get("enum"), list):
                prop["enum"] = list(field.get("enum")[:8])
            if "items" in field and isinstance(field.get("items"), dict):
                items_type = field["items"].get("type")
                if isinstance(items_type, str):
                    prop["items"] = {"type": items_type}
            if prop:
                compact_props[name] = prop
        if compact_props:
            compact["properties"] = compact_props

    required = schema.get("required")
    if isinstance(required, list) and required:
        compact["required"] = [str(x) for x in required[:12] if str(x).strip()]

    return compact or {"type": "object"}
