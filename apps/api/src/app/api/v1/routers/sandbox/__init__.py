"""
Sandbox API v2 — session-first architecture.

Sub-routers:
- sessions.py  — Sessions CRUD
- branches.py  — Branches + branch overrides + snapshots
- overrides.py — Session-level overrides
- runs.py      — Runs list/detail/execute/confirm
- catalog.py   — Components tree for sidebar
"""
from fastapi import APIRouter

from app.api.v1.routers.sandbox.sessions import router as sessions_router
from app.api.v1.routers.sandbox.branches import router as branches_router
from app.api.v1.routers.sandbox.overrides import router as overrides_router
from app.api.v1.routers.sandbox.runs import router as runs_router
from app.api.v1.routers.sandbox.catalog import router as catalog_router

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

router.include_router(sessions_router)
router.include_router(branches_router)
router.include_router(overrides_router)
router.include_router(runs_router)
router.include_router(catalog_router)
