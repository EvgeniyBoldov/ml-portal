"""
Collections data endpoints facade.
"""
from fastapi import APIRouter

from .documents import router as documents_router
from .table import router as table_router

router = APIRouter()
router.include_router(table_router)
router.include_router(documents_router)

__all__ = ["router"]
