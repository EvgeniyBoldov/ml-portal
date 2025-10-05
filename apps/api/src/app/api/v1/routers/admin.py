"""
Admin endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import db_session, require_admin, get_current_user
from core.security import UserCtx

router = APIRouter(tags=["admin"])

@router.get("/admin/status")
async def get_admin_status(
    session: AsyncSession = Depends(db_session),
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
async def set_admin_mode(
    mode_data: dict,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Set maintenance/readonly mode"""
    readonly = mode_data.get("readonly", False)
    message = mode_data.get("message", "")
    
    # TODO: Implement actual mode setting
    return {"ok": True}

@router.post("/admin/users")
async def create_admin_user(
    user_data: dict = Body(...),
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Create a new user (admin only)"""
    import uuid
    from datetime import datetime
    
    # Extract user data
    login = user_data.get("login")
    email = user_data.get("email")
    role = user_data.get("role", "reader")
    password = user_data.get("password")
    is_active = user_data.get("is_active", True)
    
    if not login:
        raise HTTPException(status_code=400, detail="login is required")
    
    # Generate a mock user
    user_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    
    mock_user = {
        "id": user_id,
        "login": login,
        "email": email,
        "role": role,
        "is_active": is_active,
        "created_at": now,
        "updated_at": now
    }
    
    # Generate password if not provided
    generated_password = password or f"temp_{login}_{user_id[:8]}"
    
    return {
        "user": mock_user,
        "password": generated_password
    }

@router.get("/admin/users")
async def list_admin_users(
    query: str = None,
    role: str = None,
    is_active: bool = None,
    limit: int = 20,
    cursor: str = None,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """List users (admin only)"""
    import uuid
    from datetime import datetime
    
    # Mock users data
    mock_users = [
        {
            "id": str(uuid.uuid4()),
            "login": "admin",
            "email": "admin@example.com",
            "role": "admin",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": str(uuid.uuid4()),
            "login": "editor1",
            "email": "editor@example.com",
            "role": "editor",
            "is_active": True,
            "created_at": "2024-01-02T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z"
        },
        {
            "id": str(uuid.uuid4()),
            "login": "reader1",
            "email": "reader@example.com",
            "role": "reader",
            "is_active": False,
            "created_at": "2024-01-03T00:00:00Z",
            "updated_at": "2024-01-03T00:00:00Z"
        }
    ]
    
    # Apply filters
    filtered_users = mock_users
    if query:
        filtered_users = [u for u in filtered_users if query.lower() in u["login"].lower() or (u["email"] and query.lower() in u["email"].lower())]
    if role:
        filtered_users = [u for u in filtered_users if u["role"] == role]
    if is_active is not None:
        filtered_users = [u for u in filtered_users if u["is_active"] == is_active]
    
    return {
        "users": filtered_users[:limit],
        "has_more": len(filtered_users) > limit,
        "total": len(filtered_users)
    }
