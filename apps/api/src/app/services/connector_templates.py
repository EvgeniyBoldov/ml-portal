from __future__ import annotations

from typing import Any, Dict, Optional, Type

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import AppError as ToolInstanceError


class BaseConnectorConfigTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BaseDataConnectorConfigTemplate(BaseConnectorConfigTemplate):
    binding_type: Optional[str] = None
    collection_id: Optional[str] = None
    collection_slug: Optional[str] = None
    collection_type: Optional[str] = None
    tenant_id: Optional[str] = None
    provider_kind: Optional[str] = None
    capability_domains: Optional[list[str]] = None


class SqlDataConnectorConfigTemplate(BaseDataConnectorConfigTemplate):
    database_name: str = Field(
        min_length=1,
        description="SQL database/schema name",
        validation_alias=AliasChoices("database_name", "db_name"),
    )
    schema_name: Optional[str] = Field(default=None, min_length=1)
    table_name: Optional[str] = Field(default=None, min_length=1)


class ApiDataConnectorConfigTemplate(BaseDataConnectorConfigTemplate):
    base_path: Optional[str] = Field(default=None, min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    system: Optional[str] = None
    readonly: Optional[bool] = None
    object_types: Optional[list[str]] = None


DATA_CONNECTOR_TEMPLATES: Dict[str, Type[BaseDataConnectorConfigTemplate]] = {
    "sql": SqlDataConnectorConfigTemplate,
    "api": ApiDataConnectorConfigTemplate,
}


def normalize_data_connector_subtype(
    *,
    connector_type: str,
    connector_subtype: Optional[str],
    legacy_domain: Optional[str] = None,
) -> Optional[str]:
    if connector_type != "data":
        if str(connector_subtype or "").strip():
            raise ToolInstanceError("connector_subtype is allowed only for data connectors")
        return None

    subtype = str(connector_subtype or "").strip().lower()
    if not subtype:
        domain = str(legacy_domain or "").strip().lower()
        subtype = "sql" if domain == "sql" else "api"

    if subtype not in DATA_CONNECTOR_TEMPLATES:
        raise ToolInstanceError(f"Invalid connector_subtype '{subtype}' for data connector")
    return subtype


def validate_connector_config(
    *,
    connector_type: str,
    connector_subtype: Optional[str],
    config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    payload = dict(config or {})
    if connector_type != "data":
        return payload or None

    subtype = normalize_data_connector_subtype(
        connector_type=connector_type,
        connector_subtype=connector_subtype,
    )
    model_cls = DATA_CONNECTOR_TEMPLATES[subtype]
    try:
        validated = model_cls.model_validate(payload)
    except ValidationError as exc:
        raise ToolInstanceError(str(exc)) from exc
    return validated.model_dump(mode="json")
