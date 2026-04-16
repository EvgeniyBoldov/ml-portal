from __future__ import annotations

import re
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ValidationError, model_validator

from app.core.exceptions import AppError as ToolInstanceError
from app.models.tool_instance import InstanceKind, InstancePlacement, ToolInstance
from app.services.instance_capabilities import resolve_provider_kind

SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,254}$")


class CollectionAssetBindingContract(BaseModel):
    binding_type: str
    collection_id: Optional[str] = None
    collection_slug: Optional[str] = None
    tenant_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_reference(self) -> "CollectionAssetBindingContract":
        has_collection_id = bool(self.collection_id)
        has_slug_tenant = bool(self.collection_slug) and bool(self.tenant_id)
        if not has_collection_id and not has_slug_tenant:
            raise ValueError(
                "collection_asset binding requires collection_id or (collection_slug + tenant_id)"
            )
        return self


class ToolInstanceValidationService:
    @staticmethod
    def normalize_connector_type(value: Optional[str]) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return "data"
        if normalized not in {"data", "mcp", "model"}:
            raise ToolInstanceError(f"Invalid connector_type '{normalized}'")
        return normalized

    @staticmethod
    def derive_instance_kind(connector_type: str) -> str:
        if connector_type == "data":
            return InstanceKind.DATA.value
        return InstanceKind.SERVICE.value
    @staticmethod
    def infer_service_provider_kind(
        *,
        placement: str,
        domain: str,
        slug: str,
        local_table_service_slug: str,
        local_document_service_slug: str,
        local_runtime_service_slug: str,
    ) -> Optional[str]:
        normalized_domain = str(domain or "").strip().lower()
        normalized_slug = str(slug or "").strip().lower()

        if normalized_domain == "mcp":
            return "mcp"
        if placement == InstancePlacement.LOCAL.value:
            if normalized_domain == "collection.table" or normalized_slug == local_table_service_slug:
                return "local_tables"
            if normalized_domain == "collection.document" or normalized_slug == local_document_service_slug:
                return "local_documents"
            if normalized_slug == local_runtime_service_slug or normalized_domain == "local":
                return "local_runtime"
        return None

    @classmethod
    def normalize_config(
        cls,
        *,
        slug: str,
        instance_kind: str,
        placement: str,
        domain: str,
        config: Optional[Dict[str, Any]],
        local_table_service_slug: str,
        local_document_service_slug: str,
        local_runtime_service_slug: str,
    ) -> Optional[Dict[str, Any]]:
        normalized: Dict[str, Any] = dict(config or {})
        if instance_kind == InstanceKind.SERVICE.value:
            provider_kind = resolve_provider_kind(normalized)
            if not provider_kind:
                inferred = cls.infer_service_provider_kind(
                    placement=placement,
                    domain=domain,
                    slug=slug,
                    local_table_service_slug=local_table_service_slug,
                    local_document_service_slug=local_document_service_slug,
                    local_runtime_service_slug=local_runtime_service_slug,
                )
                if inferred:
                    normalized["provider_kind"] = inferred
        return normalized or None

    @staticmethod
    def validate_config_requirements(
        *,
        instance_kind: str,
        placement: str,
        url: str,
        config: Optional[Dict[str, Any]],
    ) -> None:
        normalized = config or {}
        provider_kind = resolve_provider_kind(normalized)
        binding_type = str(normalized.get("binding_type") or "").strip().lower()

        if (
            instance_kind == InstanceKind.SERVICE.value
            and provider_kind == "mcp"
            and placement == InstancePlacement.REMOTE.value
            and not (url or "").strip()
        ):
            raise ToolInstanceError("Remote MCP service instances require non-empty url")

        if binding_type == "collection_asset":
            try:
                CollectionAssetBindingContract.model_validate(normalized)
            except ValidationError as exc:
                raise ToolInstanceError(str(exc)) from exc

    @staticmethod
    def validate_slug(slug: str) -> None:
        if not slug or not SLUG_PATTERN.match(slug):
            raise ToolInstanceError(
                "Invalid slug: use lowercase letters, numbers, '_' or '-', start with letter, length 2-255"
            )

    @staticmethod
    def is_system_managed_instance(
        instance: ToolInstance,
        *,
        system_managed_slugs: set[str],
    ) -> bool:
        slug = str(instance.slug or "").strip().lower()
        if instance.is_local and slug in system_managed_slugs:
            return True
        provider_kind = resolve_provider_kind(instance.config)
        if instance.is_local and provider_kind in {"local_tables", "local_documents", "local_runtime"}:
            return True
        return False

    @staticmethod
    def validate_classification(instance_kind: str, placement: str) -> None:
        valid_kinds = {InstanceKind.DATA.value, InstanceKind.SERVICE.value}
        valid_placements = {InstancePlacement.LOCAL.value, InstancePlacement.REMOTE.value}
        if instance_kind not in valid_kinds:
            raise ToolInstanceError(f"Invalid instance_kind '{instance_kind}'")
        if placement not in valid_placements:
            raise ToolInstanceError(f"Invalid placement '{placement}'")

    @staticmethod
    async def validate_access_link(
        *,
        repo,
        connector_type: str,
        access_via_instance_id: Optional[UUID],
        current_instance_id: Optional[UUID] = None,
    ) -> None:
        if access_via_instance_id is None:
            return
        if connector_type != "data":
            raise ToolInstanceError("access_via_instance_id is allowed only for data connectors")
        if current_instance_id and access_via_instance_id == current_instance_id:
            raise ToolInstanceError("Instance cannot reference itself via access_via_instance_id")

        access_instance = await repo.get_by_id(access_via_instance_id)
        if not access_instance:
            raise ToolInstanceError(f"access_via instance '{access_via_instance_id}' not found")
        access_connector_type = str(getattr(access_instance, "connector_type", "") or "").strip().lower()
        access_kind = str(getattr(access_instance, "instance_kind", "") or "").strip().lower()
        access_domain = str(getattr(access_instance, "domain", "") or "").strip().lower()
        access_provider_kind = resolve_provider_kind(getattr(access_instance, "config", None))

        is_mcp_connector = (
            access_connector_type == "mcp"
            or (
                not access_connector_type
                and access_kind == "service"
                and (access_provider_kind == "mcp" or access_domain == "mcp")
            )
        )
        if not is_mcp_connector:
            raise ToolInstanceError("access_via_instance_id must point to an mcp connector")
