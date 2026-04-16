"""Services package exports (lazy-loaded to avoid import cycles)."""

from __future__ import annotations

from importlib import import_module
from typing import Dict, Tuple

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "AgentService": ("app.services.agent_service", "AgentService"),
    "AgentError": ("app.services.agent_service", "AgentError"),
    "AgentNotFoundError": ("app.services.agent_service", "AgentNotFoundError"),
    "APIKeyService": ("app.services.api_key_service", "APIKeyService"),
    "ChatStreamService": ("app.services.chat_stream_service", "ChatStreamService"),
    "CredentialService": ("app.services.credential_service", "CredentialService"),
    "IdempotencyService": ("app.services.idempotency_service", "IdempotencyService"),
    "MCPAuditService": ("app.services.mcp_audit_service", "MCPAuditService"),
    "PermissionService": ("app.services.permission_service", "PermissionService"),
    "EffectivePermissions": ("app.services.permission_service", "EffectivePermissions"),
    "PromptService": ("app.services.prompt_service", "PromptService"),
    "ToolService": ("app.services.tool_service", "ToolService"),
    "ToolInstanceService": ("app.services.tool_instance_service", "ToolInstanceService"),
    "ToolCatalogSyncService": ("app.services.tool_catalog_sync_service", "ToolCatalogSyncService"),
    "ToolBackendReleaseSyncService": ("app.services.tool_backend_release_sync_service", "ToolBackendReleaseSyncService"),
    "sync_tools_from_registry": ("app.services.tool_catalog_sync_service", "sync_tools_from_registry"),
    "sync_backend_releases_from_registry": ("app.services.tool_backend_release_sync_service", "sync_backend_releases_from_registry"),
    "ModelService": ("app.services.model_service", "ModelService"),
    "ModelResolver": ("app.services.model_resolver", "ModelResolver"),
    "ModelHealthChecker": ("app.services.model_health_checker", "ModelHealthChecker"),
    "RAGStatusManager": ("app.services.rag_status_manager", "RAGStatusManager"),
    "RAGUploadService": ("app.services.rag_upload_service", "RAGUploadService"),
    "RAGEventPublisher": ("app.services.rag_event_publisher", "RAGEventPublisher"),
    "RAGEventSubscriber": ("app.services.rag_event_publisher", "RAGEventSubscriber"),
    "RunStore": ("app.services.run_store", "RunStore"),
    "ExecutionTraceLogger": ("app.services.execution_trace_logger", "ExecutionTraceLogger"),
    "calculate_aggregate_status": ("app.services.status_aggregator", "calculate_aggregate_status"),
    "AsyncTenantsService": ("app.services.tenants_service", "AsyncTenantsService"),
    "extract_text": ("app.services.text_extractor", "extract_text"),
    "AsyncUsersService": ("app.services.users_service", "AsyncUsersService"),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str):
    mapping = _EXPORTS.get(name)
    if mapping is None:
        raise AttributeError(name)
    module_name, attr_name = mapping
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
