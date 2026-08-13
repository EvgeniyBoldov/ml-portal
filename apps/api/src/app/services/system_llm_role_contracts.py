from __future__ import annotations

from typing import Any, Dict, Type, TYPE_CHECKING
from functools import lru_cache

from pydantic import BaseModel

from app.models.system_llm_role import SystemLLMRoleType
from app.services.system_llm_role_examples import get_role_examples

if TYPE_CHECKING:
    from app.runtime.planner.graph_planner import PlannerGraphOutput
    from app.runtime.memory.fact_extractor import _LLMFactOutput


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
        from app.runtime.planner.graph_planner import PlannerGraphOutput
        model = PlannerGraphOutput
    elif role == SystemLLMRoleType.FACT_EXTRACTOR:
        from app.runtime.memory.fact_extractor import _LLMFactOutput
        model = _LLMFactOutput
    elif role == SystemLLMRoleType.FACT_COMPACTOR:
        from app.runtime.memory.fact_compactor import _CompactionOutput
        model = _CompactionOutput
    elif role == SystemLLMRoleType.MEMORY:
        from app.runtime.memory.preparer import _PreparationOutput
        model = _PreparationOutput
    if model:
        _ROLE_OUTPUT_MODELS[role] = model

    return model


def _enrich_schema_with_contract_metadata(schema: Dict[str, Any], role: SystemLLMRoleType) -> Dict[str, Any]:
    """Add contract-specific metadata (x_when, oneOf variants) to generated JSON schema."""
    if role == SystemLLMRoleType.PLANNER:
        props = schema.get("properties", {})
        if "tasks" in props:
            props["tasks"]["description"] = "Complete task graph mutation; every task has executor, intent, instructions, dependencies and needs."

    elif role == SystemLLMRoleType.FACT_EXTRACTOR:
        # Add scope enum to fact items
        items = schema.get("properties", {}).get("facts", {}).get("items", {})
        if items and "properties" in items:
            scope_prop = items["properties"].get("scope", {})
            scope_prop["enum"] = ["user", "tenant", "project"]

    elif role == SystemLLMRoleType.FACT_COMPACTOR:
        items = schema.get("properties", {}).get("facts", {}).get("items", {})
        if items and "properties" in items:
            items["properties"].get("scope", {})["enum"] = ["user", "tenant", "project"]

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

    if role == SystemLLMRoleType.SYNTHESIZER:
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
        SystemLLMRoleType.FACT_EXTRACTOR,
        SystemLLMRoleType.FACT_COMPACTOR,
        SystemLLMRoleType.MEMORY,
    ]

    for role in json_roles:
        try:
            model = _get_output_model(role)
            if model is None:
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
