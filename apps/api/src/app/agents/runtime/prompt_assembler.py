"""Prompt assembler for runtime-facing agent prompts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from app.agents.protocol import build_operations_prompt
from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer
from app.agents.runtime.policy import PolicyLimits

if TYPE_CHECKING:
    from app.agents.contracts import ResolvedDataInstance, ResolvedOperation
    from app.agents.execution_preflight import ExecutionRequest


@dataclass(slots=True)
class PromptAssembly:
    base_prompt: str
    collection_prompt: str = ""
    operations_prompt: str = ""
    system_prompt: str = ""
    sections: List[str] = field(default_factory=list)


class CollectionPromptRenderer:
    @staticmethod
    def render(payload: Dict[str, Any]) -> str:
        name = _text(payload.get("name")) or _text(payload.get("slug")) or "collection"
        slug = _text(payload.get("slug"))
        collection_type = _text(payload.get("domain")) or _text(payload.get("instance_kind")) or "data"
        summary = _text(payload.get("summary"))
        entity_types = _normalize_str_list(payload.get("entity_types"))
        use_cases = _text(payload.get("use_cases"))
        limitations = _text(payload.get("limitations"))
        schema_hints = payload.get("schema_hints") if isinstance(payload.get("schema_hints"), dict) else {}
        examples = payload.get("examples")
        semantic_source = _text(payload.get("semantic_source"))

        lines: List[str] = [f"### {name}"]
        if slug:
            lines.append(f"- Slug: `{slug}`")
        if collection_type:
            lines.append(f"- Type: {collection_type}")
        if semantic_source:
            lines.append(f"- Source: {semantic_source}")
        if summary:
            lines.append(f"- Summary: {summary}")
        if entity_types:
            lines.append(f"- Entity types: {', '.join(entity_types)}")
        if use_cases:
            lines.append(f"- Use cases: {use_cases}")
        if limitations:
            lines.append(f"- Limitations: {limitations}")
        retrieval_profile = _text(schema_hints.get("retrieval_profile"))
        if retrieval_profile:
            lines.append(f"- Retrieval profile: {retrieval_profile}")
        rerank_mode = _text(schema_hints.get("rerank_mode"))
        if rerank_mode:
            lines.append(f"- Rerank mode: {rerank_mode}")

        field_groups = [
            ("System fields", schema_hints.get("system_fields")),
            ("Specific fields", schema_hints.get("specific_fields")),
            ("User fields", schema_hints.get("user_fields")),
        ]
        formatted_groups = [
            f"{title}: {_format_field_group(fields)}"
            for title, fields in field_groups
            if _format_field_group(fields)
        ]
        if formatted_groups:
            lines.append(f"- Fields: {'; '.join(formatted_groups)}")

        filterable_fields = _normalize_str_list(schema_hints.get("filterable_fields"))
        if filterable_fields:
            lines.append(f"- Filterable: {', '.join(filterable_fields)}")

        sortable_fields = _normalize_str_list(schema_hints.get("sortable_fields"))
        if sortable_fields:
            lines.append(f"- Sortable: {', '.join(sortable_fields)}")

        prompt_context_fields = _normalize_str_list(schema_hints.get("prompt_context_fields"))
        if prompt_context_fields:
            lines.append(f"- Prompt context fields: {', '.join(prompt_context_fields)}")

        retrieval_fields = _normalize_str_list(schema_hints.get("retrieval_fields"))
        if retrieval_fields:
            lines.append(f"- Retrieval fields: {', '.join(retrieval_fields)}")

        policy_hints = schema_hints.get("policy_hints") if isinstance(schema_hints.get("policy_hints"), dict) else {}
        if policy_hints:
            lines.extend(_format_policy_hint_lines(policy_hints))

        if examples not in (None, {}, []):
            formatted_examples = _format_examples(examples)
            if formatted_examples:
                lines.append(f"- Examples: {formatted_examples}")

        return "\n".join(lines)


class OperationPromptRenderer:
    @staticmethod
    def render_schema(op: "ResolvedOperation") -> Dict[str, Any]:
        description_parts: List[str] = []
        if op.description:
            description_parts.append(op.description)
        elif op.name:
            description_parts.append(op.name)
        if getattr(op, "resource", None):
            description_parts.append(f"Resource: {op.resource}")
        if getattr(op, "systems", None):
            description_parts.append(f"Systems: {', '.join(op.systems)}")
        if getattr(op, "return_summary", None):
            description_parts.append(f"Returns: {op.return_summary}")
        return {
            "type": "function",
            "function": {
                "name": op.operation_slug,
                "description": " | ".join(description_parts) if description_parts else op.operation_slug,
                "parameters": op.input_schema or {},
            },
        }


class PromptAssembler:
    def __init__(
        self,
        agent_renderer: Optional[AgentPromptRenderer] = None,
        collection_renderer: Optional[CollectionPromptRenderer] = None,
        operation_renderer: Optional[OperationPromptRenderer] = None,
    ) -> None:
        self.agent_renderer = agent_renderer or AgentPromptRenderer()
        self.collection_renderer = collection_renderer or CollectionPromptRenderer()
        self.operation_renderer = operation_renderer or OperationPromptRenderer()

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
        base_prompt = self.agent_renderer.render_base_prompt(
            exec_request,
            system_prompt_override=system_prompt_override,
            sandbox_overrides=sandbox_overrides,
        )
        collection_prompt = self.assemble_collection_prompt(exec_request.resolved_data_instances)
        constraints_prompt = self.assemble_constraints_prompt(
            exec_request=exec_request,
            policy_limits=resolved_policy_limits,
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
        )
        if operation_schemas is None and resolved_operations is not None:
            operation_schemas = self.assemble_operation_schemas(resolved_operations)
        operations_prompt = build_operations_prompt(operation_schemas) if operation_schemas else ""
        sections = [
            section for section in [base_prompt, collection_prompt, constraints_prompt, operations_prompt]
            if section
        ]
        return PromptAssembly(
            base_prompt=base_prompt,
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
        return "## Available Collections\n\n" + "\n\n".join(blocks)

    def assemble_constraints_prompt(
        self,
        *,
        exec_request: "ExecutionRequest",
        policy_limits: PolicyLimits,
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        blocks: List[str] = []
        blocks.append(
            "### Runtime Limits\n"
            + "\n".join([
                f"- Max steps: {policy_limits.max_steps}",
                f"- Max tool calls total: {policy_limits.max_tool_calls_total}",
                f"- Max wall time (ms): {policy_limits.max_wall_time_ms}",
                f"- Tool timeout (ms): {policy_limits.tool_timeout_ms}",
                f"- Max retries: {policy_limits.max_retries}",
                f"- Streaming enabled: {policy_limits.streaming_enabled}",
                f"- Citations required: {policy_limits.citations_required}",
                f"- Parallel tool calls allowed: {policy_limits.allow_parallel_tool_calls}",
            ])
        )
        if exec_request.policy_data:
            blocks.append(f"### Policy Version\n{_compact_json(exec_request.policy_data)}")
        if exec_request.limit_data:
            blocks.append(f"### Limit Version\n{_compact_json(exec_request.limit_data)}")

        platform_lines: List[str] = []
        if isinstance(platform_config, dict):
            policies_text = _text(platform_config.get("policies_text"))
            if policies_text:
                platform_lines.append(f"- Policies: {policies_text}")
            for key in ("abs_max_steps", "abs_max_timeout_s", "abs_max_retries", "abs_max_tool_calls_per_step"):
                value = platform_config.get(key)
                if value is not None:
                    platform_lines.append(f"- {key}: {value}")
        if platform_lines:
            blocks.append("### Platform Constraints\n" + "\n".join(platform_lines))

        sandbox_lines = self._extract_sandbox_notes(sandbox_overrides)
        if sandbox_lines:
            blocks.append("### Sandbox Notes\n" + "\n".join(f"- {line}" for line in sandbox_lines))

        policy_hints = exec_request.policy_data.get("policy_hints")
        if isinstance(policy_hints, dict) and policy_hints:
            formatted = _format_policy_hints_markdown(policy_hints)
            blocks.append(f"### Policy Hints\n{formatted or _compact_json(policy_hints)}")

        if len(blocks) == 1 and not platform_lines and not sandbox_lines and not exec_request.policy_data and not exec_request.limit_data:
            return ""
        return "## Runtime Constraints\n\n" + "\n\n".join(blocks)

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


def _format_field_group(fields: Any) -> str:
    if not isinstance(fields, list):
        return ""
    parts: List[str] = []
    for field in fields[:10]:
        if not isinstance(field, dict):
            continue
        name = _text(field.get("name"))
        if not name:
            continue
        field_type = _text(field.get("data_type"))
        parts.append(f"{name}:{field_type}" if field_type else name)
    if not parts:
        return ""
    if len(fields) > len(parts):
        parts.append(f"+{len(fields) - len(parts)} more")
    return ", ".join(parts)


def _normalize_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        normalized = _text(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return _text(value)


def _format_examples(value: Any) -> str:
    if isinstance(value, list):
        items = [item for item in (_text(item) for item in value) if item]
        return "; ".join(items)
    return _compact_json(value)


def _format_policy_hint_lines(policy_hints: Dict[str, Any]) -> List[str]:
    labels = [
        ("dos", "Do"),
        ("donts", "Don't"),
        ("guardrails", "Guardrails"),
        ("citation_rules", "Citation rules"),
        ("sensitive_fields", "Sensitive fields"),
    ]
    lines: List[str] = []
    for key, label in labels:
        items = _normalize_str_list(policy_hints.get(key))
        if items:
            lines.append(f"- {label}: {'; '.join(items)}")
    return lines


def _format_policy_hints_markdown(policy_hints: Dict[str, Any]) -> str:
    lines = _format_policy_hint_lines(policy_hints)
    return "\n".join(lines)
