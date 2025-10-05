
from fastapi import APIRouter
from api.deps import is_auth_enabled
from api.v1.routers import security as security_router
from api.v1.routers import health as health_router
from api.v1.routers import admin as admin_router
from api.v1.routers import analyze as analyze_router
from api.v1.routers import artifacts as artifacts_router
from api.v1.routers import chat as chat_router
from api.v1.routers import rag as rag_router
from api.v1.routers import users as users_router
from api.v1 import tenants as tenants_router
from api.v1 import jobs as jobs_router
from api.v1 import models as models_router
# from api.v1.routers import auth as deprecated_auth_router  # kept for compat, not mounted

api_v1 = APIRouter()

# Mount core routers here (health, users, chats, rag, etc.)

# Health endpoints - always available
api_v1.include_router(health_router.router, tags=["health"])

# Auth: mount exactly once at '/auth'
api_v1.include_router(security_router.router, prefix="/auth", tags=["auth"])

# Admin endpoints
api_v1.include_router(admin_router.router, tags=["admin"])

# Analyze endpoints
api_v1.include_router(analyze_router.router, prefix="/analyze", tags=["analyze"])

# Artifacts endpoints
api_v1.include_router(artifacts_router.router, prefix="/artifacts", tags=["artifacts"])

# Chat endpoints
api_v1.include_router(chat_router.router, prefix="/chat", tags=["chat"])

# RAG endpoints
api_v1.include_router(rag_router.router, prefix="/rag", tags=["rag"])

# Users endpoints
api_v1.include_router(users_router.router, tags=["users"])

# Tenants endpoints
api_v1.include_router(tenants_router.router, prefix="/tenants", tags=["tenants"])

# Jobs endpoints
api_v1.include_router(jobs_router.router, tags=["jobs"])

# Models endpoints
api_v1.include_router(models_router.router, prefix="/models", tags=["models"])
