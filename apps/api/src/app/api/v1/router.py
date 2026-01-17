"""
API v1 Router - combines all API routers.

Structure:
- /health - Health checks
- /auth - Authentication (security.py)
- /chats - Chat endpoints
- /rag - RAG module (documents, upload, download, lifecycle, status, search, stream)
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
from app.api.v1.routers.admin import router as admin_router
from app.api.mcp import router as mcp_router

api_v1 = APIRouter()

# Health endpoints - always available
api_v1.include_router(health_router.router, tags=["health"])

# Auth: mount exactly once at '/auth'
api_v1.include_router(security_router.router, prefix="/auth", tags=["auth"])

# Chat endpoints
api_v1.include_router(chat_router.router, prefix="/chats", tags=["chat"])

# RAG endpoints (modular: documents, upload, download, lifecycle, status, search, stream)
api_v1.include_router(rag_router, prefix="/rag", tags=["rag"])

# API Keys endpoints (for IDE plugin auth)
api_v1.include_router(api_keys_router.router, prefix="/api-keys", tags=["api-keys"])

# Profile endpoints (user profile and API tokens)
api_v1.include_router(profile_router.router, tags=["profile"])

# Admin endpoints (users, tenants, models, prompts, tools, agents, agent-runs, audit-logs)
api_v1.include_router(admin_router)

# MCP (Model Context Protocol) endpoint for IDE integration
api_v1.include_router(mcp_router, tags=["mcp"])
