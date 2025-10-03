
from fastapi import APIRouter
from app.api.deps import is_auth_enabled
from app.api.v1.routers import security as security_router
from app.api.v1.routers import health as health_router
# from app.api.v1.routers import auth as deprecated_auth_router  # kept for compat, not mounted

api_v1 = APIRouter()

# Mount core routers here (health, users, chats, rag, etc.)

# Health endpoints - always available
api_v1.include_router(health_router.router, tags=["health"])

# Auth: mount exactly once at '/auth'
api_v1.include_router(security_router.router, prefix="/auth", tags=["auth"])
