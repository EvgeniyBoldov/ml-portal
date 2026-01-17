"""
Profile API - User profile and API tokens management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from uuid import UUID
import secrets
import hashlib

from app.api.deps import get_current_user
from app.core.db import get_session_factory
from app.core.security import UserCtx
from app.models.user import Users
from app.models.api_token import ApiToken
from sqlalchemy import select

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileResponse(BaseModel):
    id: str
    login: str
    email: Optional[str]
    role: str
    created_at: datetime
    tenants: List[str] = []


class ApiTokenCreate(BaseModel):
    name: str
    scopes: Optional[str] = "mcp,chat,rag"
    expires_days: Optional[int] = None  # None = never expires


class ApiTokenResponse(BaseModel):
    id: str
    name: str
    token_prefix: str
    scopes: Optional[str]
    is_active: bool
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime


class ApiTokenCreatedResponse(ApiTokenResponse):
    token: str  # Full token, shown only once


async def get_user_from_db(user_ctx: UserCtx) -> Users:
    """Get full user object from database"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Users).where(Users.id == UUID(user_ctx.id))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user


@router.get("/me", response_model=ProfileResponse)
async def get_profile(current_user: UserCtx = Depends(get_current_user)):
    """Get current user profile"""
    user = await get_user_from_db(current_user)
    return ProfileResponse(
        id=str(user.id),
        login=user.login,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        tenants=current_user.tenant_ids or [],
    )


@router.get("/tokens", response_model=List[ApiTokenResponse])
async def list_tokens(current_user: UserCtx = Depends(get_current_user)):
    """List user's API tokens"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ApiToken)
            .where(ApiToken.user_id == UUID(current_user.id))
            .order_by(ApiToken.created_at.desc())
        )
        tokens = result.scalars().all()
        
        return [
            ApiTokenResponse(
                id=str(t.id),
                name=t.name,
                token_prefix=t.token_prefix,
                scopes=t.scopes,
                is_active=t.is_active,
                last_used_at=t.last_used_at,
                expires_at=t.expires_at,
                created_at=t.created_at,
            )
            for t in tokens
        ]


@router.post("/tokens", response_model=ApiTokenCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    data: ApiTokenCreate,
    current_user: UserCtx = Depends(get_current_user)
):
    """Create a new API token. The full token is shown only once."""
    # Generate secure token
    raw_token = secrets.token_urlsafe(32)
    token_prefix = raw_token[:8]
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    
    # Calculate expiration
    expires_at = None
    if data.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_days)
    
    session_factory = get_session_factory()
    async with session_factory() as session:
        token = ApiToken(
            user_id=UUID(current_user.id),
            name=data.name,
            token_hash=token_hash,
            token_prefix=token_prefix,
            scopes=data.scopes,
            expires_at=expires_at,
        )
        session.add(token)
        await session.commit()
        await session.refresh(token)
        
        return ApiTokenCreatedResponse(
            id=str(token.id),
            name=token.name,
            token_prefix=token.token_prefix,
            scopes=token.scopes,
            is_active=token.is_active,
            last_used_at=token.last_used_at,
            expires_at=token.expires_at,
            created_at=token.created_at,
            token=raw_token,  # Show full token only once
        )


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    token_id: UUID,
    current_user: UserCtx = Depends(get_current_user)
):
    """Delete an API token"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ApiToken).where(
                ApiToken.id == token_id,
                ApiToken.user_id == UUID(current_user.id)
            )
        )
        token = result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found"
            )
        
        await session.delete(token)
        await session.commit()


async def verify_api_token(token: str) -> Optional[tuple[Users, ApiToken]]:
    """Verify API token and return user if valid"""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ApiToken, Users)
            .join(Users, ApiToken.user_id == Users.id)
            .where(
                ApiToken.token_hash == token_hash,
                ApiToken.is_active == True,
                Users.is_active == True,
            )
        )
        row = result.first()
        
        if not row:
            return None
        
        api_token, user = row
        
        # Check expiration
        if api_token.expires_at and api_token.expires_at < datetime.now(timezone.utc):
            return None
        
        # Update last_used_at
        api_token.last_used_at = datetime.now(timezone.utc)
        await session.commit()
        
        return user, api_token
