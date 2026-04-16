"""
Admin Router - combines all admin sub-routers.

Endpoints for managing users, tenants, models, prompts, tools, agents, and observability.
"""
from fastapi import APIRouter

from .users import router as users_router
from .tenants import router as tenants_router
from .models import router as models_router
from .agents import router as agents_router
from .agent_runs import router as agent_runs_router
from .audit_logs import router as audit_logs_router
from .collections import router as collections_router
from .tool_instances import router as tool_instances_router
from .tools import router as tools_router
from .credentials import router as credentials_router
from .routing_logs import router as routing_logs_router
from .rbac import router as rbac_router
from .platform_settings import router as platform_settings_router
from .orchestration import router as orchestration_router
from .ai_generate import router as ai_generate_router
from .system_llm_roles import router as system_llm_roles_router
from .discovered_tools import router as discovered_tools_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(users_router, prefix="/users", tags=["users"])
router.include_router(tenants_router, prefix="/tenants", tags=["tenants"])
router.include_router(models_router, prefix="/models", tags=["models"])
router.include_router(agents_router, prefix="/agents", tags=["agents"])
router.include_router(agent_runs_router, prefix="/agent-runs", tags=["agent-runs"])
router.include_router(audit_logs_router, prefix="/audit-logs", tags=["audit-logs"])
router.include_router(collections_router, prefix="/collections", tags=["collections"])
router.include_router(tool_instances_router, prefix="/connectors", tags=["connectors"])
# Backward compatibility for legacy frontend/API clients.
router.include_router(tool_instances_router, prefix="/tool-instances", tags=["tool-instances"])
router.include_router(tools_router, prefix="/tools", tags=["tools"])
router.include_router(credentials_router, prefix="/credentials", tags=["credentials"])
router.include_router(routing_logs_router, prefix="/routing-logs", tags=["routing-logs"])
router.include_router(rbac_router, prefix="/rbac", tags=["rbac"])
router.include_router(platform_settings_router, prefix="/settings", tags=["platform"])
router.include_router(orchestration_router, prefix="/orchestration", tags=["orchestration"])
router.include_router(ai_generate_router, tags=["ai-generate"])
router.include_router(system_llm_roles_router, tags=["system-llm-roles"])
router.include_router(discovered_tools_router, prefix="/discovered-tools", tags=["discovered-tools"])

__all__ = ["router"]
