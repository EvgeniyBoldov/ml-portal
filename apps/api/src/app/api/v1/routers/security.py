
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, get_current_user, rate_limit_dependency
from app.repositories.users_repo import AsyncUsersRepository
from app.services.users_service import AsyncUsersService
from app.services.ldap_user_service import LDAPUserService
from app.core.security import create_access_token, create_refresh_token, decode_jwt, UserCtx
from app.core.config import get_settings, Settings

router = APIRouter(tags=["security"])

class LoginRequest(BaseModel):
    login: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    login: str | None = None
    fio: str | None = None

class LoginResponse(BaseModel):
    """Login response - tokens in httpOnly cookies, user in body"""
    access_token: str  # Kept for backward compatibility, but should be ignored by client
    refresh_token: str  # Kept for backward compatibility, but should be ignored by client
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
    user = await local_service.authenticate_user(payload.login, payload.password)
    
    # If local auth failed and LDAP is enabled, try LDAP
    if not user and settings.AUTH_LDAP_ENABLED:
        ldap_service = LDAPUserService(session, settings)
        ldap_result = await ldap_service.authenticate_and_provision(payload.login, payload.password)
        if ldap_result.success and ldap_result.user:
            user = ldap_result.user
            is_ldap_new = ldap_result.is_new
        elif ldap_result.error and "Local user with this login already exists" in ldap_result.error:
            # Conflict: local user exists, deny LDAP login
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials (local user exists, LDAP login denied)"
            )
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    # Get user's tenant IDs from database
    from sqlalchemy import text
    result = await session.execute(
        text("SELECT tenant_id FROM user_tenants WHERE user_id = :user_id"),
        {"user_id": user.id}
    )
    tenant_ids = [str(row[0]) for row in result.fetchall()]
    
    # Create JWT tokens
    access_token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role or "reader",
        tenant_ids=tenant_ids,
        scopes=getattr(user, "scopes", []) or []
    )
    
    refresh_token = create_refresh_token(str(user.id))
    
    # Set HTTP-only cookies for security
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.JWT_ACCESS_TTL_MINUTES * 60,  # 15 minutes
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    
    response.set_cookie(
        key="refresh_token", 
        value=refresh_token,
        max_age=settings.JWT_REFRESH_TTL_DAYS * 24 * 60 * 60,  # 30 days
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    
    # Return user info + tokens (tokens for backward compatibility, will be ignored by new client)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
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
    try:
        # Read refresh token from cookie
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found in cookies"
            )
        
        # Decode refresh token
        payload_data = decode_jwt(refresh_token)
        
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

        # Load tenant mapping from DB (same source as login).
        from sqlalchemy import text
        tenant_rows = await session.execute(
            text("SELECT tenant_id FROM user_tenants WHERE user_id = :user_id"),
            {"user_id": user.id},
        )
        tenant_ids = [str(row[0]) for row in tenant_rows.fetchall()]
        
        # Create new access token
        access_token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role or "reader",
            tenant_ids=tenant_ids,
            scopes=getattr(user, "scopes", []) or []
        )
        
        # Create new refresh token
        new_refresh_token = create_refresh_token(str(user.id))
        
        # Update cookies
        settings = get_settings()
        response.set_cookie(
            key="access_token",
            value=access_token,
            max_age=settings.JWT_ACCESS_TTL_MINUTES * 60,
            httponly=True,
            secure=False,
            samesite="lax"
        )
        
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            max_age=settings.JWT_REFRESH_TTL_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=False,
            samesite="lax"
        )
        
        # Get user info for response
        user_response = UserResponse(
            id=str(user.id),
            email=user.email,
            role=user.role or "reader",
            login=user.email,
            fio=getattr(user, "fio", None)
        )
        
        return LoginResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=settings.JWT_ACCESS_TTL_MINUTES * 60,
            user=user_response
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
async def logout(response: Response):
    """Logout endpoint (client-side token invalidation)"""
    # Clear cookies
    response.delete_cookie(key="access_token", httponly=True, samesite="lax")
    response.delete_cookie(key="refresh_token", httponly=True, samesite="lax")
    return None

@router.get("/.well-known/jwks.json", tags=["security"])
async def jwks():
    """JWKS endpoint for JWT key validation"""
    from app.core.security import get_jwks
    return get_jwks()
