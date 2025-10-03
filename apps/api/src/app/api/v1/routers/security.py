
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, get_current_user
from app.repositories.users_repo import AsyncUsersRepository
from app.services.users_service import AsyncUsersService
from app.core.security import create_access_token, create_refresh_token, decode_jwt, UserCtx

router = APIRouter(tags=["security"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

@router.post("/login", response_model=TokenPair, tags=["auth"])
async def login(payload: LoginRequest, session: AsyncSession = Depends(db_session)):
    service = AsyncUsersService(AsyncUsersRepository(session))
    user = await service.authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    # Create JWT tokens
    access_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role or "reader",
        tenant_ids=user.tenant_ids or [],
        scopes=user.scopes or []
    )
    
    refresh_token = create_refresh_token(str(user.id))
    
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=15 * 60  # 15 minutes
    )

@router.post("/refresh", response_model=TokenPair, tags=["auth"])
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(db_session)):
    try:
        # Decode refresh token
        payload_data = decode_jwt(payload.refresh_token)
        
        if payload_data.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload_data["sub"]
        
        # Get user data to create new access token
        service = AsyncUsersService(AsyncUsersRepository(session))
        user = await service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Create new access token
        access_token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role or "reader",
            tenant_ids=user.tenant_ids or [],
            scopes=user.scopes or []
        )
        
        # Create new refresh token
        new_refresh_token = create_refresh_token(str(user.id))
        
        return TokenPair(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=15 * 60  # 15 minutes
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

@router.get("/me", tags=["auth"])
async def me(user: UserCtx = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "tenant_ids": user.tenant_ids,
        "scopes": user.scopes
    }

@router.post("/logout", status_code=204, tags=["auth"])
async def logout():
    """Logout endpoint (client-side token invalidation)"""
    return None

@router.get("/.well-known/jwks.json", tags=["security"])
async def jwks():
    """JWKS endpoint for JWT key validation"""
    from app.core.security import get_jwks
    return get_jwks()
