"""
API v1 Router - combines all API routers.

Structure:
- /health - Health checks
- /auth - Authentication (security.py)
- /chats - Chat endpoints
- /rag - RAG module (documents, upload, download, lifecycle, status, search, stream)
- /collections - Dynamic data collections (CRUD, CSV upload, search)
- /admin/* - Admin endpoints (users, tenants, models, prompts, tools, agents, audit-logs)
- /mcp - Model Context Protocol for IDE integration
"""
from fastapi import APIRouter

from app.api.v1.routers import security as security_router
from app.api.v1.routers import health as health_router
from app.api.v1.routers import chat as chat_router
from app.api.v1.routers import profile as profile_router
from app.api.v1.routers.rag import router as rag_router
from app.api.v1.routers.collections import router as collections_router
from app.api.v1.routers.admin import router as admin_router
from app.api.v1.routers.files import router as files_router
from app.api.v1.routers.internal_mcp_credentials import router as internal_mcp_credentials_router
from app.api.v1.routers.internal_hipporag import router as internal_hipporag_router
from app.api.mcp import router as mcp_router
from app.api.v1.routers.sandbox import router as sandbox_router
from app.api.v1.routers.monitoring import router as monitoring_router

from app.api.v1.routers.shadow_agents import router as shadow_agents_router

api_v1 = APIRouter()
api_v1.include_router(shadow_agents_router)

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

# Profile endpoints (user profile and API tokens)
api_v1.include_router(profile_router.router, tags=["profile"])

# Unified file delivery endpoints
api_v1.include_router(files_router)

# Internal MCP credential broker resolve endpoint
api_v1.include_router(internal_mcp_credentials_router)
api_v1.include_router(internal_hipporag_router)

# Admin endpoints (users, tenants, models, prompts, tools, agents, audit-logs)
api_v1.include_router(admin_router)

# MCP (Model Context Protocol) endpoint for IDE integration
api_v1.include_router(mcp_router, tags=["mcp"])

# Sandbox (agent testing with config overrides)
api_v1.include_router(sandbox_router)

# Monitoring endpoints (metrics and health observability)
api_v1.include_router(monitoring_router)
