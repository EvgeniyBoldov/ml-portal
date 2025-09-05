from __future__ import annotations
import hashlib, uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from sqlalchemy.orm import Session

from app.repositories.users_repo import UsersRepo
from app.core.security import verify_password, encode_jwt, decode_jwt
from app.core.config import settings
from app.models.user import UserRefreshTokens

def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _now() -> datetime:
    return datetime.now(timezone.utc)

def login(session: Session, login: str, password: str) -> Tuple[str, str, uuid.UUID]:
    repo = UsersRepo(session)
    user = repo.by_login(login)
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("invalid_credentials")
    sub = str(user.id)
    access = encode_jwt({"sub": sub, "typ": "access"}, ttl_seconds=settings.ACCESS_TTL_SECONDS)
    refresh = encode_jwt({"sub": sub, "typ": "refresh"}, ttl_seconds=settings.REFRESH_TTL_DAYS * 86400)
    # persist refresh (hashed)
    rec = UserRefreshTokens(
        user_id=user.id,
        refresh_hash=_hash_refresh(refresh),
        issued_at=_now(),
        expires_at=_now() + timedelta(days=settings.REFRESH_TTL_DAYS),
        rotating=settings.REFRESH_ROTATING,
        revoked=False,
        meta=None,
    )
    repo.add_refresh(rec)
    return access, refresh, user.id

def refresh(session: Session, refresh_token: str) -> Tuple[str, Optional[str]]:
    payload = decode_jwt(refresh_token)
    if payload.get("typ") != "refresh":
        raise ValueError("not_refresh")
    sub = payload.get("sub")
    if not sub:
        raise ValueError("invalid_refresh")
    repo = UsersRepo(session)
    rec = repo.get_refresh_by_hash(_hash_refresh(refresh_token))
    if not rec or rec.revoked:
        raise ValueError("revoked")
    if rec.expires_at and rec.expires_at < _now():
        raise ValueError("expired")
    # rotate if configured
    access = encode_jwt({"sub": str(sub), "typ": "access"}, ttl_seconds=settings.ACCESS_TTL_SECONDS)
    if rec.rotating and settings.REFRESH_ROTATING:
        rec.revoked = True
        new_refresh = encode_jwt({"sub": str(sub), "typ": "refresh"}, ttl_seconds=settings.REFRESH_TTL_DAYS * 86400)
        new_rec = UserRefreshTokens(
            user_id=rec.user_id,
            refresh_hash=_hash_refresh(new_refresh),
            issued_at=_now(),
            expires_at=_now() + timedelta(days=settings.REFRESH_TTL_DAYS),
            rotating=True,
            revoked=False,
            meta=None,
        )
        repo.add_refresh(new_rec)
        return access, new_refresh
    # non-rotating: allow re-use
    return access, refresh_token

def revoke_refresh(session: Session, refresh_token: str) -> bool:
    return UsersRepo(session).revoke_refresh(_hash_refresh(refresh_token))
