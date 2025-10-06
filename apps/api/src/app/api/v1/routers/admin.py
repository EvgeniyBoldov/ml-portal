"""
Admin endpoints for API v1
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from api.deps import db_session, require_admin, get_current_user
from core.security import UserCtx
import uuid
from datetime import datetime

router = APIRouter(tags=["admin"])

# Global mock data storage
MOCK_USERS = [
    {
        "id": "33408253-b24c-4c81-8e30-a77e480851da",
        "login": "admin",
        "email": "admin@example.com",
        "role": "admin",
        "is_active": True,
        "tenant_id": "550e8400-e29b-41d4-a716-446655440001",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    },
    {
        "id": "560ba0ef-c680-4634-8c28-d85da467955b",
        "login": "editor1",
        "email": "editor@example.com",
        "role": "editor",
        "is_active": True,
        "tenant_id": "550e8400-e29b-41d4-a716-446655440002",
        "created_at": "2024-01-02T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z"
    },
    {
        "id": "9fb399cb-1159-4b44-883e-fde625ee17d7",
        "login": "reader1",
        "email": "reader@example.com",
        "role": "reader",
        "is_active": False,
        "tenant_id": "550e8400-e29b-41d4-a716-446655440001",
        "created_at": "2024-01-03T00:00:00Z",
        "updated_at": "2024-01-03T00:00:00Z"
    }
]

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
    # Extract user data
    login = user_data.get("login")
    email = user_data.get("email")
    role = user_data.get("role", "reader")
    password = user_data.get("password")
    is_active = user_data.get("is_active", True)
    tenant_id = user_data.get("tenant_id")
    
    if not login:
        raise HTTPException(status_code=400, detail="login is required")
    
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    
    # Check if user with this login already exists
    for user in MOCK_USERS:
        if user["login"] == login:
            raise HTTPException(status_code=400, detail="User with this login already exists")
    
    # Generate a new user
    user_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    
    new_user = {
        "id": user_id,
        "login": login,
        "email": email,
        "role": role,
        "is_active": is_active,
        "tenant_id": tenant_id,
        "created_at": now,
        "updated_at": now
    }
    
    # Add to global storage
    MOCK_USERS.append(new_user)
    
    # Generate password if not provided
    generated_password = password or f"temp_{login}_{user_id[:8]}"
    
    return {
        "user": new_user,
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
    # Apply filters to global storage
    filtered_users = MOCK_USERS.copy()
    
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

@router.get("/admin/users/{user_id}")
async def get_admin_user(
    user_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get user by ID (admin only)"""
    # Find user by ID in global storage
    for user in MOCK_USERS:
        if user["id"] == user_id:
            return user
    
    raise HTTPException(status_code=404, detail="User not found")

@router.put("/admin/users/{user_id}")
async def update_admin_user(
    user_id: str,
    user_data: dict = Body(...),
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Update user by ID (admin only)"""
    # Find user by ID in global storage
    for i, user in enumerate(MOCK_USERS):
        if user["id"] == user_id:
            # Update user data
            updated_user = {**user}
            if "role" in user_data:
                updated_user["role"] = user_data["role"]
            if "email" in user_data:
                updated_user["email"] = user_data["email"]
            if "is_active" in user_data:
                updated_user["is_active"] = user_data["is_active"]
            if "tenant_id" in user_data:
                updated_user["tenant_id"] = user_data["tenant_id"]
            if "password" in user_data:
                # Password update is handled separately, just acknowledge it
                pass
            
            updated_user["updated_at"] = datetime.utcnow().isoformat() + "Z"
            MOCK_USERS[i] = updated_user
            
            return updated_user
    
    raise HTTPException(status_code=404, detail="User not found")

@router.delete("/admin/users/{user_id}")
async def delete_admin_user(
    user_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Delete user by ID (admin only)"""
    # Find user by ID in global storage and remove it
    for i, user in enumerate(MOCK_USERS):
        if user["id"] == user_id:
            MOCK_USERS.pop(i)
            return {"message": "User deleted successfully"}
    
    raise HTTPException(status_code=404, detail="User not found")

@router.get("/admin/users/{user_id}/tokens")
async def get_user_tokens(
    user_id: str,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get user tokens (admin only)"""
    # Mock tokens data
    mock_tokens = [
        {
            "id": "token_1",
            "name": "API Token",
            "created_at": "2024-01-01T00:00:00Z",
            "last_used": "2024-01-02T00:00:00Z",
            "expires_at": "2024-12-31T23:59:59Z",
            "is_active": True
        },
        {
            "id": "token_2", 
            "name": "Mobile App",
            "created_at": "2024-01-02T00:00:00Z",
            "last_used": None,
            "expires_at": "2024-12-31T23:59:59Z",
            "is_active": True
        }
    ]
    
    return {"tokens": mock_tokens}

@router.get("/admin/audit-logs")
async def get_audit_logs(
    actor_user_id: str = None,
    limit: int = 10,
    session: AsyncSession = Depends(db_session),
    admin_user = Depends(require_admin),
):
    """Get audit logs (admin only)"""
    # Mock audit logs data
    mock_logs = [
        {
            "id": "log_1",
            "actor_user_id": actor_user_id or "33408253-b24c-4c81-8e30-a77e480851da",
            "action": "user_created",
            "resource_type": "user",
            "resource_id": "new_user_id",
            "details": {"login": "newuser", "role": "reader"},
            "created_at": "2024-01-01T00:00:00Z"
        },
        {
            "id": "log_2",
            "actor_user_id": actor_user_id or "33408253-b24c-4c81-8e30-a77e480851da",
            "action": "user_updated",
            "resource_type": "user", 
            "resource_id": "updated_user_id",
            "details": {"field": "role", "old_value": "reader", "new_value": "editor"},
            "created_at": "2024-01-02T00:00:00Z"
        }
    ]
    
    return {"logs": mock_logs}
