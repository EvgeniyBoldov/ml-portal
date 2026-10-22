"""Persistence-backed refresh-token rotation and family revocation."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_refresh_session import AuthRefreshSession


class AuthRefreshSessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def issue(
        self, *, jti: UUID, family_id: UUID, user_id: UUID, expires_at: datetime
    ) -> None:
        await self.session.execute(
            delete(AuthRefreshSession).where(AuthRefreshSession.expires_at <= datetime.now(timezone.utc))
        )
        self.session.add(AuthRefreshSession(
            jti=jti, family_id=family_id, user_id=user_id, expires_at=expires_at
        ))
        await self.session.flush()

    async def rotate(
        self,
        *,
        jti: UUID,
        family_id: UUID,
        user_id: UUID,
        next_jti: UUID,
        next_expires_at: datetime,
    ) -> bool:
        row = await self.session.scalar(
            select(AuthRefreshSession)
            .where(AuthRefreshSession.jti == jti)
            .with_for_update()
        )
        if row is None or row.user_id != user_id or row.family_id != family_id:
            return False

        now = datetime.now(timezone.utc)
        if row.consumed_at is not None or row.revoked_at is not None:
            # A consumed refresh token was replayed. Revoke any still-live
            # descendant in the same login session.
            await self.session.execute(
                update(AuthRefreshSession)
                .where(
                    AuthRefreshSession.family_id == family_id,
                    AuthRefreshSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await self.session.flush()
            return False
        if row.expires_at <= now:
            return False

        row.consumed_at = now
        await self.issue(
            jti=next_jti,
            family_id=family_id,
            user_id=user_id,
            expires_at=next_expires_at,
        )
        return True

    async def revoke_family(self, *, jti: UUID, family_id: UUID, user_id: UUID) -> None:
        row = await self.session.scalar(
            select(AuthRefreshSession).where(AuthRefreshSession.jti == jti)
        )
        if row is None or row.user_id != user_id or row.family_id != family_id:
            return
        await self.session.execute(
            update(AuthRefreshSession)
            .where(
                AuthRefreshSession.family_id == family_id,
                AuthRefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.flush()

    async def family_is_active(self, *, family_id: UUID, user_id: UUID) -> bool:
        active_jti = await self.session.scalar(
            select(AuthRefreshSession.jti)
            .where(
                AuthRefreshSession.family_id == family_id,
                AuthRefreshSession.user_id == user_id,
                AuthRefreshSession.consumed_at.is_(None),
                AuthRefreshSession.revoked_at.is_(None),
                AuthRefreshSession.expires_at > datetime.now(timezone.utc),
            )
            .limit(1)
        )
        return active_jti is not None
