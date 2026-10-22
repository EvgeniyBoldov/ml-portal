"""One authentication path for JWT access tokens and personal API Bearer tokens."""
from uuid import UUID

from app.core.db import get_session_factory
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import UserCtx, decode_jwt
from app.models.user import Users
from app.models.tenant import UserTenants
from sqlalchemy import select
import inspect
from app.repositories.api_tokens_repo import ApiTokensRepository
from app.services.auth_refresh_session_service import AuthRefreshSessionService
from app.services.personal_access_token_service import PersonalAccessTokenService, TOKEN_PREFIX


class BearerAuthenticationService:
    async def authenticate(self, token: str, *, allow_api_token: bool = True) -> UserCtx:
        if token.startswith(TOKEN_PREFIX):
            if not get_settings().PAT_ENABLED:
                raise UnauthorizedError("Personal API tokens are disabled")
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
        try:
            user_id = UUID(str(payload["sub"]))
        except (TypeError, ValueError, AttributeError) as exc:
            raise UnauthorizedError("Invalid token subject") from exc

        async with get_session_factory()() as session:
            user = await session.get(Users, user_id)
            if user is None or not user.is_enabled:
                raise UnauthorizedError("Invalid or inactive user")
            family_claim = payload.get("family_id")
            if family_claim:
                try:
                    family_id = UUID(str(family_claim))
                except (TypeError, ValueError, AttributeError) as exc:
                    raise UnauthorizedError("Invalid token session") from exc
                active_session = await AuthRefreshSessionService(session).family_is_active(
                    family_id=family_id,
                    user_id=user.id,
                )
                if not active_session:
                    raise UnauthorizedError("Session has been revoked")
            memberships = []
            if hasattr(session, "execute"):
                membership_result = await session.execute(select(UserTenants).where(UserTenants.user_id == user.id))
                membership_scalars = membership_result.scalars()
                if inspect.isawaitable(membership_scalars):
                    membership_scalars = await membership_scalars
                memberships = membership_scalars.all()
                if inspect.isawaitable(memberships):
                    memberships = await memberships
            tenant_ids = await ApiTokensRepository(session).active_tenant_ids(user.id)

        # A JWT proves authentication only. Authorization attributes come from
        # the current user and membership rows so role changes take effect now.
        return UserCtx(
            id=str(user.id),
            email=user.email,
            role=("admin" if getattr(user, "is_admin", False) else ("editor" if any(getattr(m, "is_data_editor", False) for m in memberships) else "reader")),
            tenant_ids=tenant_ids,
            scopes=[],
            is_admin=getattr(user, "is_admin", False) is True,
            tenant_admin_ids=[str(m.tenant_id) for m in memberships if getattr(m, "is_tenant_admin", False)],
            data_editor_tenant_ids=[str(m.tenant_id) for m in memberships if getattr(m, "is_data_editor", False)],
        )
