"""Resolve identities asserted by an authenticated assignment connector."""
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_assignment_identity import ExternalAssignmentIdentity
from app.models.user import Users
from app.schemas.external_assignment import Connector, ExternalUser


class AssignmentIdentityNotLinked(ValueError):
    """The supplied identity cannot be resolved safely."""


class ExternalAssignmentIdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, source: Connector, identity: ExternalUser, *, allow_link: bool = False) -> Users:
        if source.type != "clouds" or identity.clouds is None:
            raise AssignmentIdentityNotLinked

        external_id = str(identity.clouds)
        key = (source.key, external_id)
        if allow_link:
            # Serialize first linking across UUID and email collisions within a source.
            await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:source, 0))"),
                                       {"source": f"assignment-identity:{source.key}"})
        link = await self.session.get(ExternalAssignmentIdentity, key)
        if link is not None:
            user = await self.session.get(Users, link.user_id)
            if user is not None and user.is_enabled and user.auth_provider == "ldap" and user.last_login_at is not None:
                return user
            raise AssignmentIdentityNotLinked

        mail = (identity.mail or "").strip().lower()
        if not allow_link or not mail:
            raise AssignmentIdentityNotLinked
        matches = (await self.session.scalars(select(Users).where(
            Users.auth_provider == "ldap",
            func.lower(func.trim(Users.email)) == mail,
        ).limit(2))).all()
        if len(matches) != 1 or not matches[0].is_enabled or matches[0].last_login_at is None:
            raise AssignmentIdentityNotLinked
        user = matches[0]
        existing = await self.session.scalar(select(ExternalAssignmentIdentity).where(
            ExternalAssignmentIdentity.source == source.key, ExternalAssignmentIdentity.user_id == user.id,
        ))
        if existing is not None:
            raise AssignmentIdentityNotLinked
        self.session.add(ExternalAssignmentIdentity(source=source.key, external_id=external_id, user_id=user.id))
        await self.session.flush()
        return user
