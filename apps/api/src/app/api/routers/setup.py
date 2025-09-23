"""
Setup endpoints for local development
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.core.db import get_session
from app.repositories.users_repo_enhanced import UsersRepository
from app.core.security import hash_password
from app.api.schemas.users import UserCreateRequest as UserCreate, UserResponse
from app.models.user import Users
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.post("/create-superuser", response_model=UserResponse)
async def create_superuser(
    login: str = "admin",
    password: str = "admin123456",
    email: str = "admin@test.com",
    session: Session = Depends(get_session)
):
    """
    Create a superuser for local development.
    Only works when DEBUG=true and no admin users exist.
    """
    # Check if we're in debug mode
    from app.core.config import settings
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Setup endpoints only available in debug mode")
    
    repo = UsersRepository(session)
    
    # Check if admin already exists
    existing_admin = session.query(Users).filter(Users.login == login).first()
    if existing_admin:
        raise HTTPException(status_code=400, detail=f"User '{login}' already exists")
    
    try:
        # Create admin user
        admin_user = repo.create_user(
            login=login,
            password_hash=hash_password(password),
            role="admin",
            email=email,
            is_active=True
        )
        
        logger.info(f"Superuser created: {login} (ID: {admin_user.id})")
        
        return UserResponse(
            id=str(admin_user.id),
            login=admin_user.login,
            email=admin_user.email,
            role=admin_user.role,
            is_active=admin_user.is_active,
            created_at=admin_user.created_at,
            updated_at=admin_user.updated_at,
            require_password_change=admin_user.require_password_change
        )
        
    except Exception as e:
        logger.error(f"Failed to create superuser: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create superuser: {str(e)}")


@router.get("/status")
async def setup_status(session: Session = Depends(get_session)):
    """
    Check setup status - whether admin user exists.
    """
    from app.core.config import settings
    
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Setup endpoints only available in debug mode")
    
    repo = UsersRepository(session)
    
    # Count admin users
    admin_count = session.query(Users).filter(Users.role == "admin").count()
    
    return {
        "debug_mode": settings.DEBUG,
        "admin_users_count": admin_count,
        "has_admin": admin_count > 0,
        "database_connected": True
    }
