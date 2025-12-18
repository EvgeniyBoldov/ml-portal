from fastapi import APIRouter
from app.api.deps import is_auth_enabled
from app.api.v1.routers import security as security_router
from app.api.v1.routers import health as health_router
# from app.api.v1.routers import admin as admin_router
from app.api.v1.routers import analyze as analyze_router
from app.api.v1.routers import artifacts as artifacts_router
from app.api.v1.routers import chat as chat_router
from app.api.v1.routers.rag import router as rag_router
from app.api.v1.routers import users as users_router
from app.api.v1.routers import rag_search as rag_search_router
from app.api.v1.routers import tenants as tenants_router
from app.api.v1.routers import models as models_router
from app.api.v1.routers import prompts as prompts_router
from app.api.v1.routers import tools as tools_router
from app.api.v1.routers import agents as agents_router
from app.api.v1.routers import agent_runs as agent_runs_router
from app.api.v1.routers import rag_status_stream as rag_status_router
from app.api.v1.routers import api_keys as api_keys_router
from app.api.v1.routers import audit_logs as audit_logs_router
from app.api.mcp import router as mcp_router
# from app.api.v1 import jobs as jobs_router  # .del - mock implementation
# from api.v1.routers import auth as deprecated_auth_router  # kept for compat, not mounted

api_v1 = APIRouter()

# Health endpoints - always available
api_v1.include_router(health_router.router, tags=["health"])

# Auth: mount exactly once at '/auth'
api_v1.include_router(security_router.router, prefix="/auth", tags=["auth"])

# # Admin endpoints
# api_v1.include_router(admin_router.router, tags=["admin"])

# Tenant endpoints
api_v1.include_router(tenants_router.router, prefix="/tenants", tags=["tenants"])

 # Admin Users endpoints
api_v1.include_router(users_router.router, prefix="/admin/users", tags=["users"])

# Analyze endpoints
api_v1.include_router(analyze_router.router, prefix="/analyze", tags=["analyze"])

# Artifacts endpoints
api_v1.include_router(artifacts_router.router, prefix="/artifacts", tags=["artifacts"])

# Chat endpoints
api_v1.include_router(chat_router.router, prefix="/chats", tags=["chat"])

# RAG endpoints (modular)
api_v1.include_router(rag_router, prefix="/rag", tags=["rag"])

# RAG search endpoints
api_v1.include_router(rag_search_router.router, prefix="/rag", tags=["rag-search"])

# RAG status stream endpoints (SSE for real-time updates)
api_v1.include_router(rag_status_router.router, prefix="/rag/status", tags=["rag-status"])

# Jobs endpoints - REMOVED (was mock implementation, see jobs.py.del)
# api_v1.include_router(jobs_router.router, tags=["jobs"])

# Models endpoints
api_v1.include_router(models_router.router, prefix="/admin/models", tags=["models"])

# Prompts endpoints
api_v1.include_router(prompts_router.router, prefix="/admin/prompts", tags=["prompts"])

# Tools endpoints
api_v1.include_router(tools_router.router, prefix="/admin/tools", tags=["tools"])

# Agents endpoints
api_v1.include_router(agents_router.router, prefix="/admin/agents", tags=["agents"])

# Agent Runs endpoints (observability)
api_v1.include_router(agent_runs_router.router, prefix="/admin/agent-runs", tags=["agent-runs"])

# API Keys endpoints (for IDE plugin auth)
api_v1.include_router(api_keys_router.router, prefix="/api-keys", tags=["api-keys"])

# Audit Logs endpoints (admin observability)
api_v1.include_router(audit_logs_router.router, prefix="/admin/audit-logs", tags=["audit-logs"])

# MCP (Model Context Protocol) endpoint for IDE integration
api_v1.include_router(mcp_router, tags=["mcp"])
