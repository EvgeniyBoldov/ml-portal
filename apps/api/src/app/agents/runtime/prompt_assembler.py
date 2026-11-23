"""Prompt assembler for runtime-facing agent prompts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from app.agents.protocol import build_tools_payload, build_tools_prompt
from app.agents.runtime.agent_prompt_renderer import AgentPromptRenderer
from app.agents.runtime.capability_card_builder import CapabilityCardBuilder
from app.services.platform_settings_defaults import PLATFORM_OPERATION_RULES_TEXT

if TYPE_CHECKING:
    from app.agents.contracts import ResolvedDataInstance, ResolvedOperation
    from app.agents.execution_preflight import ExecutionRequest


@dataclass(slots=True)
class PromptAssembly:
    base_prompt: str
    collection_prompt: str = ""
    system_operations_prompt: str = ""
    operations_prompt: str = ""
    system_prompt: str = ""
    sections: List[str] = field(default_factory=list)


class PromptAssembler:
    def __init__(
        self,
        agent_renderer: Optional[AgentPromptRenderer] = None,
        capability_card_builder: Optional[CapabilityCardBuilder] = None,
    ) -> None:
        self.agent_renderer = agent_renderer or AgentPromptRenderer()
        self.capability_card_builder = capability_card_builder or CapabilityCardBuilder()

    def assemble(
        self,
        exec_request: "ExecutionRequest",
        *,
        system_prompt_override: Optional[str] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        operation_schemas: Optional[List[Dict[str, Any]]] = None,
        resolved_operations: Optional[Sequence["ResolvedOperation"]] = None,
        platform_config: Optional[Dict[str, Any]] = None,
        runtime_task_completion: bool = False,
    ) -> PromptAssembly:
        prompt_labels = self._resolve_prompt_labels(platform_config=platform_config, sandbox_overrides=sandbox_overrides)
        prompt_budgets = self._resolve_prompt_budgets(platform_config=platform_config, sandbox_overrides=sandbox_overrides)
        native_tool_calling = bool(isinstance(platform_config, dict) and platform_config.get("native_tool_calling", False))
        base_prompt = self.agent_renderer.render_base_prompt(
            exec_request,
            system_prompt_override=system_prompt_override,
            sandbox_overrides=sandbox_overrides,
        )
        if runtime_task_completion:
            from app.runtime.task_completion_prompt import omit_legacy_completion_sections

            base_prompt = omit_legacy_completion_sections(base_prompt)
        # Older published agent versions may still mention the removed
        # ``file.create`` name. Keep the prompt aligned with the canonical
        # operation surface while those versions are being republished.
        if resolved_operations and "file.generate" in {
            str(getattr(op, "operation_slug", "")) for op in resolved_operations
        }:
            base_prompt = base_prompt.replace("file.create", "file.generate")
        collection_prompt = self.assemble_collection_prompt(
            exec_request.resolved_data_instances,
            resolved_operations=resolved_operations,
            prompt_labels=prompt_labels,
            prompt_budgets=prompt_budgets,
            # Detailed operation contracts live in native tools or the single
            # plaintext tools block below, never in the collection cards too.
            include_operation_contracts=False,
        )
        system_operations_prompt = ""
        constraints_prompt = self.assemble_constraints_prompt(
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
            prompt_labels=prompt_labels,
        )
        if operation_schemas is None and resolved_operations is not None:
            operation_schemas = self.assemble_operation_schemas(resolved_operations)
        operations_rules_override = self._resolve_operations_rules_override(
            platform_config=platform_config,
            sandbox_overrides=sandbox_overrides,
        )
        # Native function calling carries operation names, descriptions and
        # JSON Schemas in the provider's ``tools`` field. Keep the mandatory
        # usage rules in the system prompt, but avoid duplicating that contract.
        if operation_schemas and native_tool_calling:
            rules_text = operations_rules_override or PLATFORM_OPERATION_RULES_TEXT
            if not operations_rules_override:
                rules_text = rules_text.replace(
                    "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА",
                    self._label(prompt_labels, "mandatory_rules_heading", "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА"),
                    1,
                )
            system_operations_prompt = rules_text
        operations_prompt = ""
        if operation_schemas and not native_tool_calling:
            operations_prompt = build_tools_prompt(
                operation_schemas,
                mandatory_rules_text=operations_rules_override,
                prompt_labels=prompt_labels,
            )
        sections = [
            section
            for section in [
                base_prompt,
                collection_prompt,
                system_operations_prompt,
                constraints_prompt,
                operations_prompt,
            ]
            if section
        ]
        return PromptAssembly(
            base_prompt=base_prompt,
            collection_prompt=collection_prompt,
            system_operations_prompt=system_operations_prompt,
            operations_prompt=operations_prompt,
            system_prompt="\n\n".join(sections),
            sections=sections,
        )

    def assemble_collection_prompt(
        self,
        resolved_data_instances: Sequence["ResolvedDataInstance"],
        *,
        resolved_operations: Optional[Sequence["ResolvedOperation"]] = None,
        prompt_labels: Optional[Dict[str, Any]] = None,
        prompt_budgets: Optional[Dict[str, Any]] = None,
        include_operation_contracts: bool = True,
    ) -> str:
        if not resolved_data_instances or resolved_operations is None:
            return ""
        bundle = self.capability_card_builder.build(
            resolved_data_instances=resolved_data_instances,
            resolved_operations=resolved_operations,
            prompt_labels=prompt_labels,
            prompt_budgets=prompt_budgets,
            include_operation_contracts=include_operation_contracts,
        )
        return bundle.collections_card


    def assemble_constraints_prompt(
        self,
        *,
        platform_config: Optional[Dict[str, Any]] = None,
        sandbox_overrides: Optional[Dict[str, Any]] = None,
        prompt_labels: Optional[Dict[str, Any]] = None,
    ) -> str:
        labels = prompt_labels if isinstance(prompt_labels, dict) else {}
        blocks: List[str] = []

        platform_lines: List[str] = []
        if isinstance(platform_config, dict):
            policies_text = _text(platform_config.get("policies_text"))
            normalized = policies_text.strip()
            if normalized and normalized not in {"# Политики платформы", "Политики платформы"}:
                platform_lines.append(f"- {self._label(labels, 'policies_label', 'Политики')}: {normalized}")
        if platform_lines:
            blocks.append(f"{self._label(labels, 'platform_constraints_title', 'Ограничения платформы')}\n" + "\n".join(platform_lines))

        include_sandbox_notes = bool(
            isinstance(sandbox_overrides, dict)
            and sandbox_overrides.get("include_sandbox_notes_in_prompt") is True
        )
        sandbox_lines = self._extract_sandbox_notes(sandbox_overrides) if include_sandbox_notes else []
        if sandbox_lines:
            blocks.append(f"{self._label(labels, 'sandbox_notes_title', 'Заметки sandbox')}\n" + "\n".join(f"- {line}" for line in sandbox_lines))

        return "\n\n".join(blocks)

    def assemble_operation_schemas(
        self,
        resolved_operations: Sequence["ResolvedOperation"],
    ) -> List[Dict[str, Any]]:
        return build_tools_payload(list(resolved_operations))

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



def _text(value: Any) -> str:
    return str(value or "").strip()
