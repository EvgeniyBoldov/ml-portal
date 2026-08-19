"""
Collections Router - modular structure.

Combines all Collections sub-routers into a single router.
"""
from fastapi import APIRouter

from .glossary import router as glossary_router
from .project_memory import router as project_memory_router
from .crud import router as crud_router
from .upload import router as upload_router
from .stream import router as stream_router
from .templates import router as templates_router

router = APIRouter(tags=["collections"])

router.include_router(glossary_router)
router.include_router(project_memory_router)
router.include_router(crud_router)
router.include_router(upload_router)
router.include_router(stream_router)
router.include_router(templates_router)

__all__ = ["router"]
