"""
RAG Router - modular structure.

Combines all RAG sub-routers into a single router.
"""
from fastapi import APIRouter

from .documents import router as documents_router
from .upload import router as upload_router
from .download import router as download_router
from .lifecycle import router as lifecycle_router
from .status import router as status_router

router = APIRouter(tags=["rag"])

# Include all sub-routers
router.include_router(documents_router)
router.include_router(upload_router)
router.include_router(download_router)
router.include_router(lifecycle_router)
router.include_router(status_router)

__all__ = ["router"]
