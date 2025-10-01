"""
Admin endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.api.deps import db_session, require_admin, get_current_user
from app.core.security import UserCtx

router = APIRouter(tags=["admin"])

@router.get("/admin/status")
def get_admin_status(
    session: Session = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get system status for admin"""
    return {
        "services": {
            "api": "ready",
            "workers": "ready", 
            "qdrant": "ready",
            "minio": "ready"
        },
        "metrics": {
            "sse_active": 0,
            "queue_depth": 0
        }
    }

@router.post("/admin/mode")
def set_admin_mode(
    mode_data: dict,
    session: Session = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Set maintenance/readonly mode"""
    readonly = mode_data.get("readonly", False)
    message = mode_data.get("message", "")
    
    # TODO: Implement actual mode setting
    return {"ok": True}

@router.post("/admin/users")
def admin_users(
    user_data: dict = Body(...),
    session: Session = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Admin users endpoint for testing 403 errors"""
    return {"message": "Admin users endpoint"}
