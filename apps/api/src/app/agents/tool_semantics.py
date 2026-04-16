"""Runtime tool semantics normalization and lightweight enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

SideEffects = Literal["none", "write", "destructive"]
RiskLevel = Literal["low", "medium", "high"]
SemanticQuality = Literal["raw", "enriched", "curated"]
CredentialScope = Literal["any", "user_only", "tenant_only", "platform_only", "any_non_user"]

_DESTRUCTIVE_HINTS = {
    "delete",
    "destroy",
    "drop",
    "remove",
    "truncate",
    "wipe",
    "purge",
    "revoke",
}
_WRITE_HINTS = {
    "create",
    "insert",
    "add",
    "update",
    "upsert",
    "patch",
    "set",
    "replace",
    "submit",
    "approve",
    "assign",
    "move",
    "close",
    "open",
    "restart",
    "start",
    "stop",
    "run",
    "execute",
}
_NON_IDEMPOTENT_HINTS = {
    "create",
    "insert",
    "add",
    "submit",
    "open",
    "start",
    "restart",
    "run",
    "execute",
    "trigger",
}
_SENSITIVE_FIELD_HINTS = {
    "password",
    "token",
    "secret",
    "api_key",
    "key",
    "credential",
    "auth",
}


@dataclass(slots=True)
class ToolSemantics:
    title: str
    description: str
    semantic_profile: Dict[str, Any] = field(default_factory=dict)
    policy_hints: Dict[str, Any] = field(default_factory=dict)
    side_effects: SideEffects = "none"
    risk_level: RiskLevel = "low"
    idempotent: bool = True
    requires_confirmation: bool = False
    credential_scope: CredentialScope = "any"
    risk_flags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    quality: SemanticQuality = "raw"


def build_tool_semantics(
    *,
    slug: str,
    source: str,
    discovered_name: Optional[str],
    discovered_description: Optional[str],
    input_schema: Optional[Dict[str, Any]],
    domains: Optional[List[str]],
    instance_slug: str,
    instance_domain: str,
    instance_config: Optional[Dict[str, Any]],
    provider_config: Optional[Dict[str, Any]],
    draft_semantic_overrides: Optional[Dict[str, Any]] = None,
) -> ToolSemantics:
    tokens = _collect_tokens(slug, discovered_name, discovered_description)
    side_effects = _detect_side_effects(tokens)
    risk_level = _risk_from_side_effects(side_effects)
    idempotent = _is_idempotent(tokens, side_effects)
    requires_confirmation = side_effects in ("write", "destructive")
    risk_flags = _collect_risk_flags(source, side_effects, input_schema)

    generated_title = _build_title(discovered_name, slug)
    generated_description = _build_description(
        slug=slug,
        description=discovered_description,
        side_effects=side_effects,
        domains=domains or [],
        instance_slug=instance_slug,
        instance_domain=instance_domain,
    )

    semantics = ToolSemantics(
        title=generated_title,
        description=generated_description,
        side_effects=side_effects,
        risk_level=risk_level,
        idempotent=idempotent,
        requires_confirmation=requires_confirmation,
        credential_scope="any",
        risk_flags=risk_flags,
        quality="enriched",
    )

    override = _resolve_semantic_override(slug, instance_config, provider_config)
    if override:
        _apply_semantic_override(semantics, override)
        semantics.quality = "curated"
    if isinstance(draft_semantic_overrides, dict):
        _apply_semantic_override(semantics, draft_semantic_overrides)
        semantics.quality = "curated"

    return semantics


def _collect_tokens(slug: str, name: Optional[str], description: Optional[str]) -> set[str]:
    parts = [slug or "", name or "", description or ""]
    joined = " ".join(parts).lower()
    normalized = []
    for ch in joined:
        if ch.isalnum():
            normalized.append(ch)
        else:
            normalized.append(" ")
    return set("".join(normalized).split())


def _detect_side_effects(tokens: set[str]) -> SideEffects:
    if tokens & _DESTRUCTIVE_HINTS:
        return "destructive"
    if tokens & _WRITE_HINTS:
        return "write"
    return "none"


def _risk_from_side_effects(side_effects: SideEffects) -> RiskLevel:
    if side_effects == "destructive":
        return "high"
    if side_effects == "write":
        return "medium"
    return "low"


def _is_idempotent(tokens: set[str], side_effects: SideEffects) -> bool:
    if side_effects == "destructive":
        return False
    return not bool(tokens & _NON_IDEMPOTENT_HINTS)


def _collect_risk_flags(
    source: str,
    side_effects: SideEffects,
    input_schema: Optional[Dict[str, Any]],
) -> List[str]:
    flags: List[str] = []
    if source == "mcp":
        flags.append("external_io")
    if side_effects == "write":
        flags.append("writes_data")
    if side_effects == "destructive":
        flags.append("destructive")

    properties = (input_schema or {}).get("properties") or {}
    property_names = {str(name).lower() for name in properties.keys()}
    if property_names & _SENSITIVE_FIELD_HINTS:
        flags.append("sensitive_input")
    return flags


def _build_title(discovered_name: Optional[str], slug: str) -> str:
    if discovered_name and discovered_name.strip():
        return discovered_name.strip()
    leaf = (slug or "").split(".")[-1].replace("_", " ").strip()
    return leaf.title() if leaf else "Tool Operation"


def _build_description(
    *,
    slug: str,
    description: Optional[str],
    side_effects: SideEffects,
    domains: List[str],
    instance_slug: str,
    instance_domain: str,
) -> str:
    if description and description.strip():
        return description.strip()

    domains_txt = ", ".join(domains) if domains else instance_domain
    return (
        f"Operation '{slug}' for instance '{instance_slug}' "
        f"(domain: {domains_txt}, side_effects: {side_effects})."
    )


def _resolve_semantic_override(
    slug: str,
    instance_config: Optional[Dict[str, Any]],
    provider_config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for cfg in (instance_config or {}, provider_config or {}):
        semantics = cfg.get("tool_semantics")
        if isinstance(semantics, dict):
            semantic_override = semantics.get(slug)
            if isinstance(semantic_override, dict):
                return semantic_override
    return None


def _apply_semantic_override(semantics: ToolSemantics, override: Dict[str, Any]) -> None:
    semantic_profile = override.get("semantic_profile")
    if isinstance(semantic_profile, dict):
        semantics.semantic_profile = _normalize_semantic_profile(semantic_profile)
        summary = semantics.semantic_profile.get("summary")
        if summary:
            semantics.description = summary
        examples = semantics.semantic_profile.get("examples")
        if isinstance(examples, list):
            semantics.examples = [str(item).strip() for item in examples if str(item).strip()]

    policy_hints = override.get("policy_hints")
    if isinstance(policy_hints, dict):
        semantics.policy_hints = _normalize_policy_hints(policy_hints)

    title = override.get("title")
    if isinstance(title, str) and title.strip():
        semantics.title = title.strip()

    description = override.get("description")
    if isinstance(description, str) and description.strip():
        semantics.description = description.strip()

    side_effects = override.get("side_effects")
    if side_effects in ("none", "write", "destructive"):
        semantics.side_effects = side_effects
        semantics.risk_level = _risk_from_side_effects(side_effects)
        semantics.requires_confirmation = side_effects in ("write", "destructive")

    risk_level = override.get("risk_level")
    if risk_level in ("low", "medium", "high"):
        semantics.risk_level = risk_level

    idempotent = override.get("idempotent")
    if isinstance(idempotent, bool):
        semantics.idempotent = idempotent

    requires_confirmation = override.get("requires_confirmation")
    if isinstance(requires_confirmation, bool):
        semantics.requires_confirmation = requires_confirmation

    credential_scope = override.get("credential_scope")
    if credential_scope in ("any", "user_only", "tenant_only", "platform_only", "any_non_user"):
        semantics.credential_scope = credential_scope

    risk_flags = override.get("risk_flags")
    if isinstance(risk_flags, list):
        semantics.risk_flags = [str(item) for item in risk_flags if str(item).strip()]

def _normalize_semantic_profile(value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "summary": _clean_text(value.get("summary") or value.get("description")),
        "when_to_use": _clean_text(value.get("when_to_use")),
        "limitations": _clean_text(value.get("limitations")),
        "examples": _normalize_examples(value.get("examples")),
    }


def _normalize_policy_hints(value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "dos": _normalize_lines(value.get("dos")),
        "donts": _normalize_lines(value.get("donts")),
        "guardrails": _normalize_lines(value.get("guardrails")),
        "sensitive_inputs": _normalize_lines(value.get("sensitive_inputs")),
    }


def _normalize_examples(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.splitlines()
    else:
        items = []
    result: List[str] = []
    for item in items:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _normalize_lines(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.splitlines()
    else:
        items = []
    result: List[str] = []
    for item in items:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()
