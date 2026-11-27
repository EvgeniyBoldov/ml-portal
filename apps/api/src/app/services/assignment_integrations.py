from datetime import datetime, timedelta, timezone
import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bearer_tokens import issue_token, token_matches
from app.models.assignment_integration import AssignmentIntegration, AssignmentIntegrationToken
from app.models.tool_instance import ConnectorType, ToolInstance
from app.repositories.assignment_integrations import AssignmentIntegrationsRepository

TOKEN_PREFIX = "mlp_int_"
TOKEN_PATTERN = re.compile(r"mlp_int_([0-9a-f]{32})\.[A-Za-z0-9_-]{43}\Z")


class DuplicateIntegrationSource(ValueError):
    pass


class AssignmentIntegrationsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AssignmentIntegrationsRepository(session)

    async def save(
        self, integration: AssignmentIntegration, *, name: str, connector_id: UUID, is_active: bool,
    ) -> AssignmentIntegration:
        connector = await self.session.get(ToolInstance, connector_id)
        if connector is None or connector.connector_type != ConnectorType.INTEGRATION:
            raise ValueError("Выберите коннектор типа Integration")
        integration.name = name
        integration.connector_id = connector_id
        integration.is_active = is_active
        self.session.add(integration)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise DuplicateIntegrationSource("Интеграция с таким идентификатором уже существует") from exc
            raise
        await self.session.refresh(integration)
        return integration

    async def issue(
        self, integration_id: UUID, name: str, expires_days: int | None,
    ) -> tuple[AssignmentIntegrationToken, str]:
        token_id, raw, digest = issue_token(TOKEN_PREFIX)
        expires = datetime.now(timezone.utc) + timedelta(days=expires_days) if expires_days else None
        token = AssignmentIntegrationToken(
            id=token_id, integration_id=integration_id, name=name, token_hash=digest,
            token_prefix=raw[:20], expires_at=expires, is_active=True,
        )
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token, raw

    async def revoke(self, token: AssignmentIntegrationToken) -> None:
        token.is_active = False
        await self.session.flush()

    async def authenticate(self, integration: AssignmentIntegration, raw: str) -> bool:
        match = TOKEN_PATTERN.fullmatch(raw)
        if not integration.is_active or match is None:
            return False
        token = await self.repo.token(integration.id, UUID(hex=match[1]))
        now = datetime.now(timezone.utc)
        if (
            token is None or not token.is_active
            or (token.expires_at is not None and token.expires_at <= now)
            or not token_matches(raw, token.token_hash)
        ):
            return False
        token.last_used_at = now
        return True
