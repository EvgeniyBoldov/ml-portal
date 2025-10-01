from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()

# Compose only from `api/v1/routers/*` to avoid duplicates.
# Each module is optional; missing ones are ignored gracefully.
def _include(mname: str, *, prefix: str | None = None):
    try:
        mod = __import__(f"app.api.v1.routers.{mname}", fromlist=["router"])
        r = getattr(mod, "router", None)
        if r is not None:
            router.include_router(r, prefix=prefix or "")
    except Exception:
        # module absent or invalid; we ignore to keep composition robust
        pass

_include("auth", prefix="")
_include("users", prefix="")
_include("admin", prefix="")
_include("chat", prefix="")
_include("analyze", prefix="")
_include("artifacts", prefix="")
_include("health", prefix="")
