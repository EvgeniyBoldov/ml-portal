"""
Collections document stream facade.
"""
from fastapi import APIRouter

from .stream_download import router as download_router
from .stream_events import router as events_router
from .stream_lifecycle import router as lifecycle_router

router = APIRouter()
router.include_router(events_router)
router.include_router(lifecycle_router)
router.include_router(download_router)

__all__ = ["router"]
