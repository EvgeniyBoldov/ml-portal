"""
SandboxOverrideResolver — applies branch overrides to runtime entities.

Takes effective_config (from snapshot) and applies overrides to:
- AgentVersion fields (prompt parts, execution config, safety knobs)
- OrchestrationSettings (model, temperature, timeout, max_steps)
- PlatformSettings (caps, gates, policies_text)
- SystemLLMRole configs (orchestrator prompt fields)

Does NOT mutate DB objects — creates shadow copies or override dicts.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.core.logging import get_logger
from app.services.sandbox_override_blueprints import (
    AGENT_VERSION_EXEC_FIELDS as _AGENT_VERSION_EXEC_FIELDS,
    AGENT_VERSION_PROMPT_FIELDS as _AGENT_VERSION_PROMPT_FIELDS,
    AGENT_VERSION_ALL_FIELDS as _AGENT_VERSION_ALL_FIELDS,
    PLATFORM_CAP_FIELDS as _PLATFORM_CAP_FIELDS,
    PLATFORM_GATE_FIELDS as _PLATFORM_GATE_FIELDS,
    PLATFORM_POLICY_FIELDS as _PLATFORM_POLICY_FIELDS,
    SANDBOX_BLUEPRINTS as _SANDBOX_BLUEPRINTS,
)

logger = get_logger(__name__)


class SandboxOverrideResolver:
    """
    Applies sandbox branch overrides to runtime entities.

    Usage:
        resolver = SandboxOverrideResolver(effective_config)

        # Apply to AgentVersion (returns patched shadow copy)
        patched_version = resolver.apply_agent_version(agent_version)

        # Get orchestration overrides
        orch_overrides = resolver.get_orchestration_overrides()

        # Get platform overrides
        platform_overrides = resolver.get_platform_overrides()

        # Get SystemLLMRole overrides (for triage/planner/summary)
        role_overrides = resolver.get_role_overrides(role_entity_id)
    """

    def __init__(self, effective_config: Dict[str, Any]):
        self._raw = effective_config
        self._overrides = effective_config.get("overrides", {})
        self._by_entity: Dict[str, List[Dict[str, Any]]] = {}
        self._parse_overrides()

    @classmethod
    def describe_blueprints(cls) -> List[Dict[str, Any]]:
        """Return resolver blueprints used by sandbox UI."""
        return json.loads(json.dumps(_SANDBOX_BLUEPRINTS, ensure_ascii=False))

    @classmethod
    def _field_registry(cls) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Build a registry of allowed override fields from blueprints:
        {entity_type: {field_path: field_spec}}.
        """
        registry: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for blueprint in _SANDBOX_BLUEPRINTS:
            entity_type = str(blueprint.get("entity_type") or "")
            if not entity_type:
                continue
            entity_fields = registry.setdefault(entity_type, {})
            for section in blueprint.get("sections", []):
                for field in section.get("fields", []):
                    field_path = str(field.get("field_path") or "")
                    if not field_path:
                        continue
                    entity_fields[field_path] = field
        return registry

    @classmethod
    def get_override_field_spec(
        cls,
        *,
        entity_type: str,
        field_path: str,
    ) -> Optional[Dict[str, Any]]:
        entity_fields = cls._field_registry().get(entity_type, {})
        field = entity_fields.get(field_path)
        if field is None:
            return None
        return json.loads(json.dumps(field, ensure_ascii=False))

    @classmethod
    def is_override_allowed(
        cls,
        *,
        entity_type: str,
        field_path: str,
    ) -> Tuple[bool, str]:
        registry = cls._field_registry()
        if entity_type not in registry:
            return False, f"Unsupported entity_type '{entity_type}'"
        field = registry[entity_type].get(field_path)
        if field is None:
            return False, f"Field '{field_path}' is not overridable for '{entity_type}'"
        if not bool(field.get("editable", True)):
            return False, f"Field '{field_path}' is read-only for '{entity_type}'"
        return True, ""

    @classmethod
    def schema_fingerprint(cls) -> str:
        """Stable fingerprint for snapshotting resolver shape."""
        payload = json.dumps(_SANDBOX_BLUEPRINTS, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def get_blueprint(cls, key: str) -> Optional[Dict[str, Any]]:
        for blueprint in _SANDBOX_BLUEPRINTS:
            if blueprint.get("key") == key:
                return json.loads(json.dumps(blueprint, ensure_ascii=False))
        return None

    def _parse_overrides(self) -> None:
        """Group overrides by entity_type for fast lookup."""
        for key, ov in self._overrides.items():
            entity_type = ov.get("entity_type", "")
            if entity_type not in self._by_entity:
                self._by_entity[entity_type] = []
            self._by_entity[entity_type].append(ov)

    def _iter_overrides(self, entity_type: str):
        """Iterate raw overrides for entity type."""
        for ov in self._by_entity.get(entity_type, []):
            yield ov

    @staticmethod
    def _matches_entity_id(override_entity_id: Any, entity_id: Optional[str]) -> bool:
        """Entity-id matching semantics used by per-entity methods."""
        if entity_id is None:
            return override_entity_id is None
        return str(override_entity_id or "") == str(entity_id)

    def _iter_entity_field_overrides(
        self,
        *,
        entity_type: str,
        entity_id: Optional[str],
        field_path: Optional[str] = None,
    ):
        for ov in self._iter_overrides(entity_type):
            if not self._matches_entity_id(ov.get("entity_id"), entity_id):
                continue
            if field_path is not None and ov.get("field_path") != field_path:
                continue
            yield ov

    @staticmethod
    def _nested_get(data: Dict[str, Any], path: str) -> Any:
        if "." not in path:
            return data.get(path)
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @property
    def has_overrides(self) -> bool:
        return bool(self._overrides)

    @property
    def agent_slug_override(self) -> Optional[str]:
        """Check if there's an override for tenant.default_agent_slug."""
        for ov in self._iter_overrides("orchestration"):
            if ov.get("field_path") == "tenant.default_agent_slug":
                return ov.get("value_json")
        return None

    def get_agent_version_override(self) -> Optional[str]:
        """Return forced AgentVersion ID override for sandbox runtime if set."""
        for ov in self._iter_overrides("orchestration"):
            if ov.get("field_path") != "agent.version_id":
                continue
            value = ov.get("value_json")
            if isinstance(value, UUID):
                return str(value)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def get_overrides_for_entity(
        self,
        entity_type: str,
        entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get all field overrides for a specific entity as {field_path: value_json}."""
        result: Dict[str, Any] = {}
        for ov in self._iter_entity_field_overrides(
            entity_type=entity_type,
            entity_id=entity_id,
        ):
            if not ov.get("field_path"):
                continue
            result[ov.get("field_path", "")] = ov.get("value_json")
        return result

    def get_override_entry(
        self,
        entity_type: str,
        entity_id: Optional[str],
        field_path: str,
    ) -> Optional[Dict[str, Any]]:
        """Return raw override entry for exact entity + field match."""
        for ov in self._iter_entity_field_overrides(
            entity_type=entity_type,
            entity_id=entity_id,
            field_path=field_path,
        ):
            return ov
        return None

    def resolve_field_state(
        self,
        *,
        entity_type: str,
        entity_id: Optional[str],
        field_path: str,
        base_value: Any,
    ) -> Dict[str, Any]:
        """
        Resolve canonical field state:
        - base_value (from DB-sourced entity view)
        - override_value (from branch overlay)
        - effective_value (base + overlay)
        """
        override = self.get_override_entry(entity_type, entity_id, field_path)
        has_override = override is not None
        override_value = override.get("value_json") if override else None
        return {
            "field_path": field_path,
            "base_value": base_value,
            "override_value": override_value,
            "effective_value": override_value if has_override else base_value,
            "is_overridden": has_override,
        }

    def resolve_blueprint_state(
        self,
        *,
        blueprint_key: str,
        entity_id: Optional[str],
        source: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build resolver state for a blueprint using source object:
        - sections with field-level base/override/effective values.
        """
        blueprint = self.get_blueprint(blueprint_key)
        if blueprint is None:
            return {
                "blueprint_key": blueprint_key,
                "entity_type": "",
                "entity_id": entity_id,
                "sections": [],
            }

        entity_type = str(blueprint.get("entity_type") or "")
        sections_out: List[Dict[str, Any]] = []

        for section in blueprint.get("sections", []):
            fields_out: List[Dict[str, Any]] = []
            for field in section.get("fields", []):
                source_key = field.get("source_key") or field.get("key") or field.get("field_path")
                field_path = str(field.get("field_path") or "")
                base_value = self._nested_get(source, str(source_key))
                field_state = self.resolve_field_state(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_path=field_path,
                    base_value=base_value,
                )
                fields_out.append({
                    "key": field.get("key"),
                    "label": field.get("label"),
                    "field_type": field.get("field_type"),
                    "editable": field.get("editable", True),
                    "options": field.get("options", []),
                    "help_text": field.get("help_text"),
                    "source_key": field.get("source_key"),
                    **field_state,
                })
            sections_out.append({
                "title": section.get("title", ""),
                "fields": fields_out,
            })

        return {
            "blueprint_key": blueprint_key,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "sections": sections_out,
        }

    # ── AgentVersion ─────────────────────────────────────────────────────

    def compile_patched_prompt(self, agent_version: "AgentVersion") -> Optional[str]:
        """
        Compile a patched system prompt from AgentVersion + overrides.

        Returns patched prompt string if there are prompt overrides,
        or None if no prompt overrides exist.
        Does NOT mutate the original ORM object.
        """
        overrides = self.get_overrides_for_entity(
            "agent_version",
            str(agent_version.id),
        )
        prompt_overrides = {
            k: v for k, v in overrides.items()
            if k in _AGENT_VERSION_PROMPT_FIELDS
        }
        if not prompt_overrides:
            return None

        # Read current values from ORM object, apply overrides
        prompt_parts = {
            "identity": getattr(agent_version, "identity", None),
            "mission": getattr(agent_version, "mission", None),
            "scope": getattr(agent_version, "scope", None),
            "rules": getattr(agent_version, "rules", None),
            "tool_use_rules": getattr(agent_version, "tool_use_rules", None),
            "output_format": getattr(agent_version, "output_format", None),
            "examples": getattr(agent_version, "examples", None),
        }
        for field, value in prompt_overrides.items():
            prompt_parts[field] = value
            logger.debug(
                "Prompt override: agent_version.%s = %s",
                field,
                repr(value)[:100],
            )

        # Compile prompt same way as AgentVersion.compiled_prompt
        sections = []
        labels = {
            "identity": "Identity",
            "mission": "Mission",
            "scope": "Scope",
            "rules": "Rules",
            "tool_use_rules": "Tool Use Rules",
            "output_format": "Output Format",
            "examples": "Examples",
        }
        for key, label in labels.items():
            val = prompt_parts.get(key)
            if val:
                sections.append(f"# {label}\n{val}")

        compiled = "\n\n".join(sections) if sections else (getattr(agent_version, "prompt", None) or "")

        logger.info(
            "Applied %d prompt override(s) to AgentVersion %s",
            len(prompt_overrides),
            agent_version.id,
        )
        return compiled

    def get_agent_exec_overrides(self, agent_version: "AgentVersion") -> Dict[str, Any]:
        """
        Get execution config overrides for AgentVersion (model, temperature, etc.).

        Returns dict with keys matching AgentVersion exec fields.
        Does NOT mutate the original ORM object.
        """
        overrides = self.get_overrides_for_entity(
            "agent_version",
            str(agent_version.id),
        )
        result: Dict[str, Any] = {}
        for field, value in overrides.items():
            if field in _AGENT_VERSION_EXEC_FIELDS:
                result[field] = value
                logger.debug(
                    "Exec override: agent_version.%s = %s",
                    field,
                    repr(value)[:100],
                )
        return result

    # ── Orchestration (executor config) ──────────────────────────────────

    def get_orchestration_overrides(self) -> Dict[str, Any]:
        """
        Get orchestration overrides as a flat dict.

        Keys: executor_model, executor_temperature, executor_timeout_s, executor_max_steps.
        These are applied on top of OrchestrationSettingsProvider.get_effective_config().
        """
        result: Dict[str, Any] = {}
        # Orchestration overrides come from agent_version overrides (model, temperature, etc.)
        # but also from explicit orchestration entity_type overrides.
        for ov in self._iter_overrides("orchestration"):
            field_path = ov.get("field_path", "")
            value = ov.get("value_json")

            # Map field paths to orchestration config keys
            if field_path == "model" or field_path == "executor_model":
                result["executor_model"] = value
            elif field_path == "temperature" or field_path == "executor_temperature":
                result["executor_temperature"] = value
            elif field_path == "timeout_s" or field_path == "executor_timeout_s":
                result["executor_timeout_s"] = value
            elif field_path == "max_steps" or field_path == "executor_max_steps":
                result["executor_max_steps"] = value

        return result

    # ── Platform settings ────────────────────────────────────────────────

    def get_platform_overrides(self) -> Dict[str, Any]:
        """
        Get platform settings overrides (caps, gates, policies).

        Applied on top of PlatformSettingsProvider.get_config().
        """
        result: Dict[str, Any] = {}
        for ov in self._iter_overrides("orchestration"):
            field_path = ov.get("field_path", "")
            value = ov.get("value_json")

            # platform.* prefix from frontend
            if field_path.startswith("platform."):
                key = field_path[len("platform."):]
                if key in _PLATFORM_CAP_FIELDS | _PLATFORM_GATE_FIELDS | _PLATFORM_POLICY_FIELDS:
                    result[key] = value

        return result

    # ── Tenant overrides ─────────────────────────────────────────────────

    def get_tenant_overrides(self) -> Dict[str, Any]:
        """Get tenant-level overrides (default_agent_slug, etc.)."""
        result: Dict[str, Any] = {}
        for ov in self._iter_overrides("orchestration"):
            field_path = ov.get("field_path", "")
            value = ov.get("value_json")

            if field_path.startswith("tenant."):
                key = field_path[len("tenant."):]
                result[key] = value

        return result

    # ── SystemLLMRole (triage/planner/summary router configs) ────────────

    def get_role_overrides(self, entity_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get overrides for a SystemLLMRole config (orchestrator).

        These modify the prompt fields of triage/planner/summary roles.
        """
        return self.get_overrides_for_entity("orchestration", entity_id)

    # ── ToolRelease overrides ────────────────────────────────────────────

    def get_tool_release_overrides(self, release_id: str) -> Dict[str, Any]:
        """Get overrides for a specific ToolRelease."""
        return self.get_overrides_for_entity("tool_release", release_id)

    def get_tool_publication_overrides(self) -> Dict[str, bool]:
        """Get sandbox publication flags for discovered tools."""
        result: Dict[str, bool] = {}
        for ov in self._iter_overrides("discovered_tool"):
            field_path = ov.get("field_path", "")
            if field_path != "published":
                continue
            entity_id = ov.get("entity_id")
            if not entity_id:
                continue
            value = ov.get("value_json")
            if isinstance(value, bool):
                result[str(entity_id)] = value
        return result

    def get_discovered_tool_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Get semantic overrides for discovered tools."""
        result: Dict[str, Dict[str, Any]] = {}
        for ov in self._iter_overrides("discovered_tool"):
            field_path = ov.get("field_path", "")
            if field_path in {"published", "tool_release_id", "source", "slug", "domains", "input_schema", "output_schema"}:
                continue
            entity_id = ov.get("entity_id")
            if not entity_id:
                continue
            entry = result.setdefault(str(entity_id), {})
            value = ov.get("value_json")
            if field_path == "description" and isinstance(value, str):
                entry["description"] = value
            elif field_path == "name" and isinstance(value, str):
                entry["title"] = value
            else:
                entry[field_path] = value
        return result

    def get_discovered_tool_release_overrides(self) -> Dict[str, str]:
        """Return selected ToolRelease IDs for discovered tools: {discovered_tool_id: tool_release_id}."""
        result: Dict[str, str] = {}
        for ov in self._iter_overrides("discovered_tool"):
            if ov.get("field_path") != "tool_release_id":
                continue
            entity_id = ov.get("entity_id")
            if not entity_id:
                continue
            value = ov.get("value_json")
            if isinstance(value, UUID):
                result[str(entity_id)] = str(value)
                continue
            if isinstance(value, str) and value.strip():
                result[str(entity_id)] = value.strip()
        return result

    # ── Unified runtime overrides ───────────────────────────────────────

    def to_runtime_overrides(
        self,
        agent_version: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Convert all sandbox overrides into a single dict for ToolContext.extra["sandbox_overrides"].

        This is the **only** method sandbox needs to call — runtime picks up
        everything from ctx.extra["sandbox_overrides"].

        Args:
            agent_version: AgentVersion ORM object (for prompt/exec overrides).

        Returns:
            Dict with keys: orchestration, platform, prompt, agent_exec, logging_level.
        """
        result: Dict[str, Any] = {
            "orchestration": self.get_orchestration_overrides(),
            "platform": self.get_platform_overrides(),
            "logging_level": "full",  # sandbox always full
            "tool_publication": self.get_tool_publication_overrides(),
            "discovered_tool_overrides": self.get_discovered_tool_overrides(),
            "discovered_tool_release_ids": self.get_discovered_tool_release_overrides(),
        }

        if agent_version is not None:
            patched_prompt = self.compile_patched_prompt(agent_version)
            if patched_prompt is not None:
                result["prompt"] = patched_prompt
            agent_exec = self.get_agent_exec_overrides(agent_version)
            if agent_exec:
                result["agent_exec"] = agent_exec

        return result

    # ── Summary ──────────────────────────────────────────────────────────

    def describe(self) -> Dict[str, Any]:
        """Return human-readable summary of active overrides."""
        summary: Dict[str, Any] = {"total": len(self._overrides)}
        for entity_type, items in self._by_entity.items():
            summary[entity_type] = [
                {
                    "entity_id": ov.get("entity_id"),
                    "field": ov.get("field_path"),
                    "value_preview": repr(ov.get("value_json"))[:80],
                }
                for ov in items
            ]
        return summary
