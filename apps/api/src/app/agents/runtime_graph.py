from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget


class OperationRuntimeContext(BaseModel):
    instance_id: str = Field(..., min_length=1)
    instance_slug: str = Field(..., min_length=1)
    provider_instance_id: str = Field(..., min_length=1)
    provider_instance_slug: str = Field(..., min_length=1)
    has_credentials: bool = False
    credential_scope: str = "auto"
    config: Dict[str, Any] = Field(default_factory=dict)
    provider_config: Dict[str, Any] = Field(default_factory=dict)
    domain: str = Field(..., min_length=1)
    data_instance_url: Optional[str] = None
    provider_url: Optional[str] = None


class OperationExecutionBinding(BaseModel):
    operation_slug: str = Field(..., min_length=1)
    target: ProviderExecutionTarget
    context: OperationRuntimeContext
    credential: Optional[OperationCredentialContext] = None


class RuntimeExecutionGraph(BaseModel):
    bindings: Dict[str, OperationExecutionBinding] = Field(default_factory=dict)

    def add(self, binding: OperationExecutionBinding) -> None:
        self.bindings[binding.operation_slug] = binding

    def get(self, operation_slug: str) -> Optional[OperationExecutionBinding]:
        return self.bindings.get(operation_slug)

    def filter_by_operation_slugs(self, allowed_operation_slugs: set[str]) -> None:
        self.bindings = {
            slug: binding
            for slug, binding in self.bindings.items()
            if slug in allowed_operation_slugs
        }

    def merge(self, other: "RuntimeExecutionGraph") -> None:
        if not other or not other.bindings:
            return
        self.bindings.update(other.bindings)

    def to_legacy_maps(self) -> tuple[Dict[str, ProviderExecutionTarget], Dict[str, Dict[str, Any]], Dict[str, OperationCredentialContext]]:
        execution_targets: Dict[str, ProviderExecutionTarget] = {}
        operation_context_map: Dict[str, Dict[str, Any]] = {}
        operation_credentials_map: Dict[str, OperationCredentialContext] = {}
        for slug, binding in self.bindings.items():
            execution_targets[slug] = binding.target
            operation_context_map[slug] = binding.context.model_dump()
            if binding.credential is not None:
                operation_credentials_map[slug] = binding.credential
        return execution_targets, operation_context_map, operation_credentials_map
