from __future__ import annotations

from typing import Any, Dict, Type, TYPE_CHECKING
from functools import lru_cache

from pydantic import BaseModel

from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_examples import get_role_examples

if TYPE_CHECKING:
    from app.runtime.planner.planner import PlannerLLMOutput
    from app.runtime.memory.fact_extractor import _LLMFactOutput
    from app.runtime.memory.summary_compactor import _LLMSummaryOutput


def _json_contract(schema: Dict[str, Any], *, on_invalid: str, format_locked: bool = True) -> Dict[str, Any]:
    return {
        "format": "json",
        "schema": schema,
        "plain_text": None,
        "markdown": None,
        "examples": [],
        "examples_v2": None,
        "failure_policy": {"on_invalid": on_invalid},
        "format_locked": format_locked,
    }


def _plain_text_contract(*, on_invalid: str, criteria: list[str], forbidden: list[str], format_locked: bool = True) -> Dict[str, Any]:
    return {
        "format": "plain_text",
        "schema": None,
        "plain_text": {
            "criteria": criteria,
            "forbidden": forbidden,
        },
        "markdown": None,
        "examples": [],
        "examples_v2": None,
        "failure_policy": {"on_invalid": on_invalid},
        "format_locked": format_locked,
    }


# Registry of Pydantic output models per role (lazy import to avoid circular deps)
# These are populated at runtime by _get_output_model
_ROLE_OUTPUT_MODELS: Dict[SystemLLMRoleType, Type[BaseModel]] = {}


def _get_output_model(role: SystemLLMRoleType) -> Type[BaseModel] | None:
    """Lazy-load Pydantic models to avoid circular imports at module load time."""
    if role in _ROLE_OUTPUT_MODELS:
        return _ROLE_OUTPUT_MODELS[role]

    model: Type[BaseModel] | None = None

    if role == SystemLLMRoleType.PLANNER:
        from app.runtime.planner.planner import PlannerLLMOutput
        model = PlannerLLMOutput
    elif role == SystemLLMRoleType.FACT_EXTRACTOR:
        from app.runtime.memory.fact_extractor import _LLMFactOutput
        model = _LLMFactOutput
    elif role == SystemLLMRoleType.SUMMARY_COMPACTOR:
        from app.runtime.memory.summary_compactor import _LLMSummaryOutput
        model = _LLMSummaryOutput
    elif role == SystemLLMRoleType.TRIAGE:
        # Triage uses inline schema - no separate Pydantic model yet
        model = None

    if model:
        _ROLE_OUTPUT_MODELS[role] = model

    return model


def _enrich_schema_with_contract_metadata(schema: Dict[str, Any], role: SystemLLMRoleType) -> Dict[str, Any]:
    """Add contract-specific metadata (x_when, oneOf variants) to generated JSON schema."""
    if role == SystemLLMRoleType.PLANNER:
        # Add conditional field markers (x_when) to properties
        props = schema.get("properties", {})
        if "agent_slug" in props:
            props["agent_slug"]["x_when"] = "kind=call_agent"
        if "agent_input" in props:
            props["agent_input"]["x_when"] = "kind=call_agent"
        if "question" in props:
            props["question"]["x_when"] = "kind=clarify"
        if "final_answer" in props:
            props["final_answer"]["x_when"] = "kind=direct_answer|final"

        # Add oneOf variants for discriminated union on 'kind'
        schema["oneOf"] = [
            {
                "title": "call_agent",
                "required": ["kind", "rationale", "agent_slug", "agent_input"],
                "properties": {"kind": {"const": "call_agent"}},
            },
            {
                "title": "clarify",
                "required": ["kind", "rationale", "question"],
                "properties": {"kind": {"enum": ["clarify", "ask_user"]}},
            },
            {
                "title": "direct_or_final",
                "required": ["kind", "rationale", "final_answer"],
                "properties": {"kind": {"enum": ["direct_answer", "final"]}},
            },
            {
                "title": "abort",
                "required": ["kind", "rationale"],
                "properties": {"kind": {"const": "abort"}},
            },
        ]

    elif role == SystemLLMRoleType.FACT_EXTRACTOR:
        # Add scope enum to fact items
        items = schema.get("properties", {}).get("facts", {}).get("items", {})
        if items and "properties" in items:
            scope_prop = items["properties"].get("scope", {})
            scope_prop["enum"] = ["user", "chat", "tenant"]

    elif role == SystemLLMRoleType.SUMMARY_COMPACTOR:
        # entities is dict in model, but contract expects array of strings
        # Keep as-is from model schema
        pass

    return schema


@lru_cache(maxsize=32)
def build_response_contract(role_type: SystemLLMRoleType | str) -> Dict[str, Any]:
    """Build response contract for a system LLM role.

    JSON schemas are generated from Pydantic models to ensure contract matches
    runtime validation exactly. Contract metadata (x_when, oneOf) is added on top.
    """
    normalized = role_type.value if isinstance(role_type, SystemLLMRoleType) else str(role_type)
    role = SystemLLMRoleType(normalized)
    examples_v2 = get_role_examples(role)

    # Try to get Pydantic model for this role
    output_model = _get_output_model(role)

    if output_model is not None:
        # Generate schema from Pydantic model
        schema = output_model.model_json_schema()
        # Enrich with contract-specific metadata
        schema = _enrich_schema_with_contract_metadata(schema, role)
        contract = _json_contract(schema, on_invalid="retry_once_then_fallback", format_locked=True)
        contract["examples_v2"] = examples_v2
        return contract

    # Fallback: manual contract for roles without Pydantic models
    if role == SystemLLMRoleType.TRIAGE:
        contract = _json_contract(
            {
                "type": "object",
                "required": ["type", "confidence", "reason"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["final", "clarify", "orchestrate", "resume"],
                        "description": "Triage decision type",
                    },
                    "confidence": {"type": "number", "description": "Confidence score 0-1"},
                    "reason": {"type": "string", "description": "Explanation of decision"},
                    "answer": {"type": ["string", "null"], "description": "Answer text (when type=final)"},
                    "clarify_prompt": {"type": ["string", "null"], "description": "Clarification question (when type=clarify)"},
                    "goal": {"type": ["string", "null"], "description": "Goal for orchestration (when type=orchestrate)"},
                    "agent_hint": {"type": ["string", "null"], "description": "Suggested agent (when type=orchestrate)"},
                    "resume_run_id": {"type": ["string", "null"], "description": "Run ID to resume (when type=resume)"},
                },
            },
            on_invalid="retry_once_then_fallback",
            format_locked=True,
        )
        contract["examples_v2"] = examples_v2
        return contract

    if role in (SystemLLMRoleType.SYNTHESIZER, SystemLLMRoleType.SUMMARY, SystemLLMRoleType.MEMORY):
        contract = _plain_text_contract(
            on_invalid="accept_with_runtime_safety_filters",
            criteria=[
                "Answer must be grounded in provided context and facts",
                "Keep response concise and readable",
            ],
            forbidden=[
                "Traceback",
                "Internal identifiers",
                "Secrets or credentials",
            ],
            format_locked=True,
        )
        contract["examples_v2"] = examples_v2
        return contract

    contract = _plain_text_contract(
        on_invalid="accept_with_runtime_safety_filters",
        criteria=["Respond in plain text"],
        forbidden=["Secrets or credentials"],
        format_locked=True,
    )
    contract["examples_v2"] = examples_v2
    return contract


def get_role_output_model(role_type: SystemLLMRoleType | str) -> Type[BaseModel] | None:
    """Get the Pydantic output model class for a role (for validation/testing)."""
    normalized = role_type.value if isinstance(role_type, SystemLLMRoleType) else str(role_type)
    role = SystemLLMRoleType(normalized)
    return _get_output_model(role)


def validate_role_contracts() -> Dict[SystemLLMRoleType, str]:
    """Validate that all JSON roles have valid Pydantic models and schemas.

    Returns dict of {role: error_message} for any failures.
    Should be called at app startup to fail fast on schema divergence.
    """
    errors: Dict[SystemLLMRoleType, str] = {}
    json_roles = [
        SystemLLMRoleType.PLANNER,
        SystemLLMRoleType.TRIAGE,
        SystemLLMRoleType.FACT_EXTRACTOR,
        SystemLLMRoleType.SUMMARY_COMPACTOR,
    ]

    for role in json_roles:
        try:
            model = _get_output_model(role)
            if model is None:
                if role == SystemLLMRoleType.TRIAGE:
                    # Triage is allowed to have manual contract
                    continue
                errors[role] = f"No Pydantic output model registered for {role.value}"
                continue

            # Try to generate schema - this catches model definition errors
            schema = model.model_json_schema()
            if not schema.get("properties"):
                errors[role] = f"Schema for {role.value} has no properties"

            # Try to build full contract
            contract = build_response_contract(role)
            if contract.get("format") != "json":
                errors[role] = f"Contract for JSON role {role.value} has wrong format: {contract.get('format')}"

        except Exception as exc:
            errors[role] = f"Failed to validate {role.value}: {exc}"

    return errors
