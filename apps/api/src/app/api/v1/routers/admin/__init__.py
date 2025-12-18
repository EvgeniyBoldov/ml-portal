"""
Admin Router - combines all admin sub-routers.

Endpoints for managing users, models, prompts, tools, agents, and observability.
"""
from fastapi import APIRouter

from .users import router as users_router
from .models import router as models_router
from .prompts import router as prompts_router
from .tools import router as tools_router
from .agents import router as agents_router
from .agent_runs import router as agent_runs_router
from .audit_logs import router as audit_logs_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(users_router, prefix="/users", tags=["users"])
router.include_router(models_router, prefix="/models", tags=["models"])
router.include_router(prompts_router, prefix="/prompts", tags=["prompts"])
router.include_router(tools_router, prefix="/tools", tags=["tools"])
router.include_router(agents_router, prefix="/agents", tags=["agents"])
router.include_router(agent_runs_router, prefix="/agent-runs", tags=["agent-runs"])
router.include_router(audit_logs_router, prefix="/audit-logs", tags=["audit-logs"])

__all__ = ["router"]
