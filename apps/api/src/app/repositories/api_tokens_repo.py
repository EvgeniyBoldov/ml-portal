"""Persistence for personal API tokens; transaction ownership stays with callers."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_token import ApiToken
from app.models.user import Users
from app.models.tenant import UserTenants, Tenants


class ApiTokensRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, token: ApiToken) -> ApiToken:
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def list_owned(self, user_id: UUID) -> list[ApiToken]:
        rows = await self.session.scalars(select(ApiToken).where(ApiToken.user_id == user_id)
                                          .order_by(ApiToken.created_at.desc()))
        return list(rows.all())

    async def delete_owned(self, token_id: UUID, user_id: UUID) -> bool:
        token = await self.session.scalar(select(ApiToken).where(ApiToken.id == token_id,
                                                                ApiToken.user_id == user_id))
        if token is None:
            return False
        await self.session.delete(token)
        await self.session.flush()
        return True

    async def active_token_owner(self, token_id: UUID) -> tuple[ApiToken, Users] | None:
        row = (await self.session.execute(select(ApiToken, Users).join(Users, ApiToken.user_id == Users.id)
            .where(ApiToken.id == token_id, ApiToken.is_active.is_(True), Users.is_active.is_(True),
                   Users.lifecycle_status != "deprecated"))).first()
        return (row[0], row[1]) if row else None

    async def active_tenant_ids(self, user_id: UUID) -> list[str]:
        rows = await self.session.scalars(select(UserTenants.tenant_id).join(Tenants, Tenants.id == UserTenants.tenant_id)
            .where(UserTenants.user_id == user_id, Tenants.is_active.is_(True), Tenants.lifecycle_status != "deprecated")
            .order_by(UserTenants.is_default.desc(), Tenants.created_at.asc()))
        return [str(value) for value in rows.all()]

    async def record_use(self, token: ApiToken, used_at: datetime) -> None:
        token.last_used_at = used_at
        await self.session.flush()
