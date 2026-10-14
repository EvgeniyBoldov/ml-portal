"""One authentication path for JWT access tokens and personal API Bearer tokens."""
from app.core.db import get_session_factory
from app.core.exceptions import UnauthorizedError
from app.core.security import UserCtx, decode_jwt
from app.services.personal_access_token_service import PersonalAccessTokenService, TOKEN_PREFIX


class BearerAuthenticationService:
    async def authenticate(self, token: str, *, allow_api_token: bool = True) -> UserCtx:
        if token.startswith(TOKEN_PREFIX):
            if not allow_api_token:
                raise UnauthorizedError("API tokens require Authorization: Bearer")
            async with get_session_factory()() as session:
                user = await PersonalAccessTokenService(session).authenticate(token)
                if user is None:
                    raise UnauthorizedError("Invalid or expired API token")
                # This dedicated auth transaction owns only usage bookkeeping.
                await session.commit()
                return user
        payload = decode_jwt(token)
        if payload.get("type") != "access" or not payload.get("sub"):
            raise UnauthorizedError("Invalid token type")
        return UserCtx(id=payload["sub"], email=payload.get("email"), role=payload.get("role", "reader"),
                       tenant_ids=payload.get("tenant_ids", []), scopes=payload.get("scopes", []))
