# Consolidated FastAPI entrypoint: routers-only, no controllers imports.
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ML-Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "version": "v1"}

try:
    from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
    Instrumentator().instrument(app).expose(app)
except Exception:
    pass

def _include_router_safe(module_path: str, attr: str = "router", prefix: str | None = None) -> None:
    try:
        module = __import__(module_path, fromlist=[attr])
        router = getattr(module, attr, None)
        if router is not None:
            if prefix:
                app.include_router(router, prefix=prefix)
            else:
                app.include_router(router)
    except Exception as e:
        print(f"[main] skip {module_path}: {e}")

# Routers only
_include_router_safe("app.api.routers.auth")
_include_router_safe("app.api.routers.admin")
_include_router_safe("app.api.routers.chats")
_include_router_safe("app.api.routers.rag")
_include_router_safe("app.api.routers.analyze")
_include_router_safe("app.api.routers.users")
