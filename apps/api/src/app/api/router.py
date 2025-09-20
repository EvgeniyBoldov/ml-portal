from __future__ import annotations
from fastapi import APIRouter
from app.core.config import settings

from .routers import rag_search
# If your project has these modules available, they will be included as well.
try:
    from .rag import router as rag_router
except Exception:
    rag_router = None
try:
    from .chats import router as chats_router
except Exception:
    chats_router = None
try:
    from .auth import router as auth_router
except Exception:
    auth_router = None
try:
    from .routers.admin import router as admin_router
except Exception:
    admin_router = None

api_v1 = APIRouter(prefix=settings.API_V1_PREFIX)

if auth_router:
    api_v1.include_router(auth_router)
if rag_router:
    api_v1.include_router(rag_router)
if chats_router:
    api_v1.include_router(chats_router)
api_v1.include_router(rag_search.router)
if admin_router:
    api_v1.include_router(admin_router)
