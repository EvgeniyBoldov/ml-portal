from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment_integration import AssignmentIntegration, AssignmentIntegrationToken


class AssignmentIntegrationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_source(self, source: str) -> AssignmentIntegration | None:
        return await self.session.scalar(select(AssignmentIntegration).where(AssignmentIntegration.source == source))

    async def has_connector(self, connector_id: UUID) -> bool:
        query = select(AssignmentIntegration.id).where(AssignmentIntegration.connector_id == connector_id).limit(1)
        return await self.session.scalar(query) is not None

    async def list_integrations(self) -> list[AssignmentIntegration]:
        return list(await self.session.scalars(select(AssignmentIntegration).order_by(AssignmentIntegration.name)))

    async def list_tokens(self, integration_id: UUID) -> list[AssignmentIntegrationToken]:
        query = select(AssignmentIntegrationToken).where(
            AssignmentIntegrationToken.integration_id == integration_id,
        ).order_by(AssignmentIntegrationToken.created_at.desc())
        return list(await self.session.scalars(query))

    async def token(self, integration_id: UUID, token_id: UUID) -> AssignmentIntegrationToken | None:
        token = await self.session.get(AssignmentIntegrationToken, token_id)
        return token if token and token.integration_id == integration_id else None
