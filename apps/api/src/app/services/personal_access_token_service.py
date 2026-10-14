"""Personal Bearer tokens: public lookup id plus a cryptographically random secret."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserCtx
from app.models.api_token import ApiToken
from app.repositories.api_tokens_repo import ApiTokensRepository

TOKEN_PREFIX = "mlp_pat_"
TOKEN_PATTERN = re.compile(r"mlp_pat_([0-9a-f]{32})\.[A-Za-z0-9_-]{43}\Z")


class PersonalAccessTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = ApiTokensRepository(session)

    async def create(self, *, user_id: UUID, name: str, expires_days: int | None) -> tuple[ApiToken, str]:
        token_id = uuid4()
        raw = f"{TOKEN_PREFIX}{token_id.hex}.{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days) if expires_days else None
        token = await self.repo.create(ApiToken(id=token_id, user_id=user_id, name=name,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(), token_prefix=raw[:20],
            expires_at=expires_at, is_active=True))
        return token, raw

    async def list_owned(self, user_id: UUID) -> list[ApiToken]:
        return await self.repo.list_owned(user_id)

    async def delete_owned(self, token_id: UUID, user_id: UUID) -> bool:
        return await self.repo.delete_owned(token_id, user_id)

    async def authenticate(self, raw: str) -> UserCtx | None:
        match = TOKEN_PATTERN.fullmatch(raw)
        if match is None:
            return None
        row = await self.repo.active_token_owner(UUID(hex=match[1]))
        if row is None:
            return None
        token, user = row
        now = datetime.now(timezone.utc)
        if token.expires_at is not None and token.expires_at <= now:
            return None
        if not hmac.compare_digest(token.token_hash, hashlib.sha256(raw.encode()).hexdigest()):
            return None
        tenant_ids = await self.repo.active_tenant_ids(user.id)
        await self.repo.record_use(token, now)
        return UserCtx(id=str(user.id), email=user.email, role=user.role, tenant_ids=tenant_ids, scopes=[])
