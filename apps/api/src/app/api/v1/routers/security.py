
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session
from app.repositories.users_repo import AsyncUsersRepository
from app.services.users_service import AsyncUsersService

router = APIRouter(tags=["security"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"

@router.post("/login", response_model=TokenPair, tags=["auth"])
async def login(payload: LoginRequest, session: AsyncSession = Depends(db_session)):
    service = AsyncUsersService(AsyncUsersRepository(session))
    user = await service.authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # Minimal stub token pair for now; wire real JWT later.
    return TokenPair(access_token="stub-access", refresh_token="stub-refresh")

@router.post("/refresh", tags=["auth"])
async def refresh():
    # Stub refresh endpoint
    return {"access_token": "stub-access", "token_type": "Bearer"}

@router.get("/me", tags=["auth"])
async def me():
    # Stub 'me' endpoint; replace with real user from token
    return {"id": "stub", "email": "stub@example.com", "role": "reader", "tenant_ids": []}

@router.post("/logout", status_code=204, tags=["auth"])
async def logout():
    return None

@router.get("/.well-known/jwks.json", tags=["security"])
async def jwks():
    """JWKS endpoint for JWT key validation"""
    # Stub JWKS response
    return {
        "keys": [
            {
                "kty": "oct",
                "kid": "test-key",
                "use": "sig",
                "alg": "HS256",
                "k": "test-secret-key"
            }
        ]
    }
