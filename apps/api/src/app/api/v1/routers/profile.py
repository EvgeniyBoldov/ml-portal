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
from app.core.security import verify_password, hash_password
from app.core.security import UserCtx
from app.core.crypto import get_crypto_service
from app.models.user import Users
from app.models.api_token import ApiToken
from app.models.credential_set import Credential
from app.models.tool_instance import ToolInstance
from app.models.tool import Tool
from app.models.memory import Fact
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

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


class CredentialCreate(BaseModel):
    tool_instance_id: str
    auth_type: str = "token"
    encrypted_payload: dict


class CredentialResponse(BaseModel):
    id: str
    tool_instance_id: str
    tool_name: Optional[str] = None
    auth_type: str
    is_active: bool
    created_at: datetime


class UserFactResponse(BaseModel):
    id: str
    scope: str
    subject: str
    value: str
    confidence: float
    source: str
    observed_at: datetime
    created_at: datetime


class FactsDeleteRequest(BaseModel):
    ids: List[UUID]


class FactsDeleteResponse(BaseModel):
    deleted: int


class ProfilePasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


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


@router.get("/facts", response_model=List[UserFactResponse])
async def list_user_facts(
    current_user: UserCtx = Depends(get_current_user),
    limit: int = 200,
    offset: int = 0,
):
    """List active user-visible facts for current user."""
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    user_id = UUID(current_user.id)

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Fact)
            .where(
                Fact.user_id == user_id,
                Fact.user_visible.is_(True),
                Fact.superseded_by.is_(None),
            )
            .order_by(Fact.observed_at.desc())
            .offset(safe_offset)
            .limit(safe_limit)
        )
        rows = result.scalars().all()

    return [
        UserFactResponse(
            id=str(row.id),
            scope=row.scope,
            subject=row.subject,
            value=row.value,
            confidence=row.confidence,
            source=row.source,
            observed_at=row.observed_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete("/facts", response_model=FactsDeleteResponse)
async def delete_user_facts(
    payload: FactsDeleteRequest,
    current_user: UserCtx = Depends(get_current_user),
):
    """Soft-delete selected user facts by tombstoning active rows."""
    if not payload.ids:
        return FactsDeleteResponse(deleted=0)

    user_id = UUID(current_user.id)
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            update(Fact)
            .where(
                Fact.id.in_(payload.ids),
                Fact.user_id == user_id,
                Fact.user_visible.is_(True),
                Fact.superseded_by.is_(None),
            )
            .values(superseded_by=Fact.id)
        )
        result = await session.execute(stmt)
        await session.commit()

    return FactsDeleteResponse(deleted=result.rowcount or 0)


@router.post("/password")
async def change_profile_password(
    payload: ProfilePasswordChangeRequest,
    current_user: UserCtx = Depends(get_current_user),
):
    """Change current user's password (local accounts only)."""
    if not payload.new_password or len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="password_too_short",
        )

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(Users).where(Users.id == UUID(current_user.id)))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        auth_provider = getattr(user, "auth_provider", "local")
        if auth_provider != "local":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="password_change_not_allowed_for_non_local_accounts",
            )

        if not user.password_hash or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_current_password",
            )

        user.password_hash = hash_password(payload.new_password)
        await session.commit()

    return {"ok": True}


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


# ============================================================================
# User Credentials endpoints
# ============================================================================

@router.get("/credentials", response_model=List[CredentialResponse])
async def list_user_credentials(current_user: UserCtx = Depends(get_current_user)):
    """List user's credentials for tool instances"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Credential, ToolInstance)
            .join(ToolInstance, Credential.instance_id == ToolInstance.id)
            .where(
                Credential.owner_user_id == UUID(current_user.id),
                Credential.is_active == True,
            )
            .order_by(Credential.created_at.desc())
        )
        rows = result.all()
        
        return [
            CredentialResponse(
                id=str(cred.id),
                instance_id=str(cred.instance_id),
                owner_user_id=str(cred.owner_user_id) if cred.owner_user_id else None,
                owner_tenant_id=str(cred.owner_tenant_id) if cred.owner_tenant_id else None,
                owner_platform=cred.owner_platform,
                auth_type=cred.auth_type,
                is_active=cred.is_active,
                created_at=cred.created_at,
            )
            for cred, instance in rows
        ]


@router.post("/credentials", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_user_credential(
    data: CredentialCreate,
    current_user: UserCtx = Depends(get_current_user)
):
    """Create user credential for a tool instance"""
    crypto = get_crypto_service()
    
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Verify tool instance exists and is active
        result = await session.execute(
            select(ToolInstance).where(ToolInstance.id == UUID(data.tool_instance_id))
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tool instance not found"
            )
        
        encrypted = crypto.encrypt(data.encrypted_payload)
        
        credential = Credential(
            instance_id=UUID(data.tool_instance_id),
            owner_user_id=UUID(current_user.id),
            owner_platform=False,
            auth_type=data.auth_type,
            encrypted_payload=encrypted,
            is_active=True,
        )
        session.add(credential)
        await session.commit()
        await session.refresh(credential)
        
        return CredentialResponse(
            id=str(credential.id),
            instance_id=str(credential.instance_id),
            owner_user_id=str(credential.owner_user_id),
            owner_tenant_id=None,
            owner_platform=False,
            auth_type=credential.auth_type,
            is_active=credential.is_active,
            created_at=credential.created_at,
        )


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_credential(
    credential_id: UUID,
    current_user: UserCtx = Depends(get_current_user)
):
    """Delete user's credential"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Credential).where(
                Credential.id == credential_id,
                Credential.owner_user_id == UUID(current_user.id),
            )
        )
        credential = result.scalar_one_or_none()
        
        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credential not found"
            )
        
        await session.delete(credential)
        await session.commit()
