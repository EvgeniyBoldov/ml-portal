"""
Collections Router - modular structure.

Combines all Collections sub-routers into a single router.
"""
from fastapi import APIRouter

from .crud import router as crud_router
from .upload import router as upload_router

router = APIRouter(tags=["collections"])

router.include_router(crud_router)
router.include_router(upload_router)

__all__ = ["router"]
