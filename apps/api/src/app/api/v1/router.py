"""
app/api/v1/router.py
Mounts v1 routers. Auth is required; others are optional.
"""
from fastapi import APIRouter
from importlib import import_module

api_v1 = APIRouter()

from app.api.routes import security as security_router  # type: ignore
api_v1.include_router(security_router.router, prefix="/auth", tags=["auth"])

_optional = [
    ("app.api.routes.users", "router", "/users", ["users"]),
    ("app.api.routes.rag", "router", "/rag", ["rag"]),
    ("app.api.routes.analyze", "router", "/analyze", ["analyze"]),
    ("app.api.routes.chat", "router", "/chat", ["chat"]),
    ("app.api.routes.admin", "router", "/admin", ["admin"]),
    ("app.api.routes.artifacts", "router", "/artifacts", ["artifacts"]),
]

for module_path, attr, prefix, tags in _optional:
    try:
        mod = import_module(module_path)
        router = getattr(mod, attr, None)
        if router is not None:
            api_v1.include_router(router, prefix=prefix, tags=tags)
    except Exception:
        pass
