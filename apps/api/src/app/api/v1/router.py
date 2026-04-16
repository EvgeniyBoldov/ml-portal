"""
API v1 Router - combines all API routers.

Structure:
- /health - Health checks
- /auth - Authentication (security.py)
- /chats - Chat endpoints
- /rag - RAG module (documents, upload, download, lifecycle, status, search, stream)
- /collections - Dynamic data collections (CRUD, CSV upload, search)
- /api-keys - API keys for IDE plugin
- /admin/* - Admin endpoints (users, tenants, models, prompts, tools, agents, agent-runs, audit-logs)
- /mcp - Model Context Protocol for IDE integration
"""
from fastapi import APIRouter

from app.api.v1.routers import security as security_router
from app.api.v1.routers import health as health_router
from app.api.v1.routers import chat as chat_router
from app.api.v1.routers import api_keys as api_keys_router
from app.api.v1.routers import profile as profile_router
from app.api.v1.routers.rag import router as rag_router
from app.api.v1.routers.collections import router as collections_router
from app.api.v1.routers.admin import router as admin_router
from app.api.v1.routers.plans import router as plans_router
from app.api.v1.routers.system_llm_traces import router as system_llm_traces_router
from app.api.v1.routers.files import router as files_router
from app.api.v1.routers.internal_mcp_credentials import router as internal_mcp_credentials_router
from app.api.mcp import router as mcp_router
from app.api.v1.routers.sandbox import router as sandbox_router

api_v1 = APIRouter()

# Health endpoints - always available
api_v1.include_router(health_router.router, tags=["health"])

# Auth: mount exactly once at '/auth'
api_v1.include_router(security_router.router, prefix="/auth", tags=["auth"])

# Chat endpoints
api_v1.include_router(chat_router.router, prefix="/chats", tags=["chat"])

# RAG endpoints (modular: documents, upload, download, lifecycle, status, search, stream)
api_v1.include_router(rag_router, prefix="/rag", tags=["rag"])

# Collections endpoints (dynamic data collections)
api_v1.include_router(collections_router, prefix="/collections", tags=["collections"])

# API Keys endpoints (for IDE plugin auth)
api_v1.include_router(api_keys_router.router, prefix="/api-keys", tags=["api-keys"])

# Profile endpoints (user profile and API tokens)
api_v1.include_router(profile_router.router, tags=["profile"])

# Plans endpoints (execution plan management)
api_v1.include_router(plans_router, tags=["plans"])

# Unified file delivery endpoints
api_v1.include_router(files_router)

# Internal MCP credential broker resolve endpoint
api_v1.include_router(internal_mcp_credentials_router)

# System LLM Traces endpoints (LLM call logging and analysis)
api_v1.include_router(system_llm_traces_router, tags=["system-llm-traces"])

# Admin endpoints (users, tenants, models, prompts, tools, agents, agent-runs, audit-logs)
api_v1.include_router(admin_router)

# MCP (Model Context Protocol) endpoint for IDE integration
api_v1.include_router(mcp_router, tags=["mcp"])

# Sandbox (agent testing with config overrides)
api_v1.include_router(sandbox_router)
