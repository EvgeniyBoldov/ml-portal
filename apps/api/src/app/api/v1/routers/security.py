
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, get_current_user, rate_limit_dependency
from app.models.tenant import Tenants, UserTenants
from app.repositories.users_repo import AsyncUsersRepository
from app.services.users_service import AsyncUsersService
from app.services.ldap_user_service import LDAPUserService
from app.core.security import create_access_token, create_refresh_token, decode_jwt, UserCtx
from app.core.config import get_settings, is_local
from app.core.exceptions import UnauthorizedError
from app.services.auth_refresh_session_service import AuthRefreshSessionService

router = APIRouter(tags=["security"])


async def _load_active_tenant_ids(session: AsyncSession, user_id) -> list[str]:
    result = await session.execute(
        select(UserTenants.tenant_id)
        .join(Tenants, Tenants.id == UserTenants.tenant_id)
        .where(
            UserTenants.user_id == user_id,
            Tenants.is_active.is_(True),
            Tenants.lifecycle_status != "deprecated",
        )
        .order_by(UserTenants.is_default.desc(), Tenants.created_at.asc())
    )
    return [str(row[0]) for row in result.fetchall()]

class LoginRequest(BaseModel):
    login: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str | None = None
    role: str
    login: str | None = None
    fio: str | None = None

class LoginResponse(BaseModel):
    """Access token for in-memory use; refresh token stays in its HTTP-only cookie."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse

@router.post("/login", response_model=LoginResponse, tags=["auth"])
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(db_session),
    _rl: None = Depends(rate_limit_dependency(key_prefix="auth_login", rpm=30, rph=600)),
):
    settings = get_settings()
    users_repo = AsyncUsersRepository(session)
    local_service = AsyncUsersService(users_repo)
    
    # Try local authentication first
    try:
        user = await local_service.authenticate_user(payload.login, payload.password)
    except ValueError as exc:
        if str(exc) == "account_deprecated":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account_deprecated") from exc
        raise
    
    # If local auth failed and LDAP is enabled, try LDAP
    ldap_provisioned = False
    if not user and settings.AUTH_LDAP_ENABLED:
        ldap_service = LDAPUserService(session, settings)
        ldap_result = await ldap_service.authenticate_and_provision(payload.login, payload.password)
        if ldap_result.success and ldap_result.user:
            user = ldap_result.user
            ldap_provisioned = True
        elif ldap_result.error and "Local user with this login already exists" in ldap_result.error:
            # Conflict: local user exists, deny LDAP login
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials (local user exists, LDAP login denied)"
            )
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # db_session dependency does not auto-commit.
    # Persist JIT LDAP provisioning in the same request, otherwise user exists only
    # in transaction scope and disappears after response.
    if ldap_provisioned:
        await session.commit()
    
    tenant_ids = await _load_active_tenant_ids(session, user.id)

    refresh_jti = uuid4()
    refresh_family_id = uuid4()
    # Bind both browser tokens to one revocable server-side session family.
    access_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role or "reader",
        tenant_ids=tenant_ids,
        scopes=getattr(user, "scopes", []) or [],
        family_id=str(refresh_family_id),
    )
    
    refresh_token = create_refresh_token(
        str(user.id), jti=str(refresh_jti), family_id=str(refresh_family_id)
    )
    await AuthRefreshSessionService(session).issue(
        jti=refresh_jti,
        family_id=refresh_family_id,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TTL_DAYS),
    )
    await session.commit()
    
    # Set HTTP-only cookies for security
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.JWT_ACCESS_TTL_MINUTES * 60,  # 15 minutes
        httponly=True,
        secure=not is_local(),
        samesite="lax"
    )
    
    response.set_cookie(
        key="refresh_token", 
        value=refresh_token,
        max_age=settings.JWT_REFRESH_TTL_DAYS * 24 * 60 * 60,  # 30 days
        httponly=True,
        secure=not is_local(),
        samesite="lax"
    )
    
    # Return the short-lived access token; the refresh credential remains cookie-only.
    return LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.JWT_ACCESS_TTL_MINUTES * 60,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            role=user.role or "reader",
            login=user.login,
            fio=getattr(user, "full_name", None)
        )
    )

@router.post("/refresh", response_model=LoginResponse, tags=["auth"])
async def refresh(request: Request, response: Response, session: AsyncSession = Depends(db_session)):
    """Refresh access token using refresh token from httpOnly cookie"""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not found")

    payload_data = decode_jwt(refresh_token)
    if payload_data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    try:
        user_id = UUID(str(payload_data["sub"]))
        refresh_jti = UUID(str(payload_data["jti"]))
        family_id = UUID(str(payload_data["family_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    service = AsyncUsersService(AsyncUsersRepository(session))
    user = await service.get_user_by_id(str(user_id))
    if not user or not user.is_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    settings = get_settings()
    tenant_ids = await _load_active_tenant_ids(session, user.id)
    access_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role or "reader",
        tenant_ids=tenant_ids,
        scopes=getattr(user, "scopes", []) or [],
        family_id=str(family_id),
    )
    next_jti = uuid4()
    new_refresh_token = create_refresh_token(
        str(user.id), jti=str(next_jti), family_id=str(family_id)
    )
    rotated = await AuthRefreshSessionService(session).rotate(
        jti=refresh_jti,
        family_id=family_id,
        user_id=user.id,
        next_jti=next_jti,
        next_expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TTL_DAYS),
    )
    # Commit even on replay: rotate() revokes the active descendants on reuse.
    await session.commit()
    if not rotated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.JWT_ACCESS_TTL_MINUTES * 60,
        httponly=True,
        secure=not is_local(),
        samesite="lax",
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        max_age=settings.JWT_REFRESH_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=not is_local(),
        samesite="lax",
    )

    user_response = UserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role or "reader",
        login=user.login,
        fio=getattr(user, "full_name", None),
    )
    return LoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.JWT_ACCESS_TTL_MINUTES * 60,
        user=user_response,
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
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    """Revoke the refresh-token family and clear browser cookies."""
    raw_refresh_token = request.cookies.get("refresh_token")
    if raw_refresh_token:
        try:
            claims = decode_jwt(raw_refresh_token)
            if claims.get("type") == "refresh":
                user_id = UUID(str(claims["sub"]))
                jti = UUID(str(claims["jti"]))
                family_id = UUID(str(claims["family_id"]))
                await AuthRefreshSessionService(session).revoke_family(
                    jti=jti, family_id=family_id, user_id=user_id
                )
                await session.commit()
        except (UnauthorizedError, KeyError, TypeError, ValueError):
            # Logout remains idempotent for expired, malformed, or old cookies.
            pass
    response.delete_cookie(key="access_token", httponly=True, secure=not is_local(), samesite="lax")
    response.delete_cookie(key="refresh_token", httponly=True, secure=not is_local(), samesite="lax")
    return None

@router.get("/.well-known/jwks.json", tags=["security"])
async def jwks():
    """JWKS endpoint for JWT key validation"""
    from app.core.security import get_jwks
    return get_jwks()
