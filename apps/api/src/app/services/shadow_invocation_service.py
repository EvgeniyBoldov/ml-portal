import hashlib
import json
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.shadow_invocation import ShadowInvocation
from app.repositories.shadow_invocation_repository import ShadowInvocationRepository
from app.schemas.shadow_agents import ShadowAgentTask, ShadowAgentRequest
from app.services.shadow_agent_service import ShadowAgentService


logger = get_logger(__name__)


class ShadowInvocationService:
    def __init__(self, session: AsyncSession, agent_service: ShadowAgentService) -> None:
        self.session = session
        self.agent_service = agent_service
        self.repo = ShadowInvocationRepository(session)

    async def enqueue(self, payload: ShadowAgentRequest, *, user_id: UUID, tenant_id: UUID,
                      scopes: list[str], request_id: str,
                      idempotency_key: str | None = None) -> UUID:
        normalized_key = idempotency_key.strip() if idempotency_key is not None else None
        if normalized_key is not None and (not normalized_key or len(normalized_key) > 255):
            raise ValueError("Idempotency-Key must be nonblank and at most 255 characters")
        await self.agent_service.validate(payload, user_id=user_id, tenant_id=tenant_id)
        fingerprint = self._request_fingerprint(payload) if normalized_key is not None else None
        if normalized_key is not None:
            existing = await self.repo.by_idempotency_key(user_id=user_id, tenant_id=tenant_id,
                                                           idempotency_key=normalized_key)
            if existing is not None:
                self._validate_replay(existing, fingerprint)
                return existing.id
        row = ShadowInvocation(user_id=user_id, tenant_id=tenant_id, agent=payload.agent,
                               data=payload.data, scopes=scopes, request_id=request_id, status="queued",
                               idempotency_key=normalized_key, request_fingerprint=fingerprint)
        try:
            await self.repo.add(row)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            if normalized_key is None:
                raise
            existing = await self.repo.by_idempotency_key(user_id=user_id, tenant_id=tenant_id,
                                                           idempotency_key=normalized_key)
            if existing is None:
                raise
            self._validate_replay(existing, fingerprint)
            return existing.id
        # The row is the durable source of truth; periodic dispatch repairs a
        # broker failure between commit and publication.
        try:
            from app.workers.tasks_shadow_invocations import execute_shadow_invocation
            execute_shadow_invocation.delay(str(row.id))
        except Exception:
            logger.exception("shadow_invocation_dispatch_failed", extra={"invocation_id": str(row.id)})
        return row.id

    @staticmethod
    def _request_fingerprint(payload: ShadowAgentRequest) -> str:
        normalized = json.dumps({"agent": payload.agent, "data": payload.data},
                                ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_replay(existing: ShadowInvocation, fingerprint: str | None) -> None:
        if existing.request_fingerprint != fingerprint:
            raise ConflictError("Idempotency-Key was already used for a different request")

    @staticmethod
    def _response(row: ShadowInvocation) -> ShadowAgentTask:
        return ShadowAgentTask(id=row.id, agent=row.agent, status=row.status,
                               result=row.result, error=row.error, created_at=row.created_at,
                               delivered_at=row.delivered_at)

    async def list_ready(self, user_id: UUID, *, tenant_id: UUID | None = None,
                         tenant_ids: list[UUID] | None = None) -> list[ShadowAgentTask]:
        return [self._response(row) for row in await self.repo.ready(
            user_id, tenant_id=tenant_id, tenant_ids=tenant_ids)]

    async def get(self, invocation_id: UUID, user_id: UUID, *, tenant_id: UUID | None = None,
                  tenant_ids: list[UUID] | None = None) -> ShadowAgentTask:
        row = await self.repo.get_owned(invocation_id, user_id, tenant_id=tenant_id, tenant_ids=tenant_ids)
        if row is None:
            raise NotFoundError("Shadow invocation")
        return self._response(row)

    async def acknowledge(self, invocation_id: UUID, user_id: UUID, *, tenant_id: UUID | None = None,
                          tenant_ids: list[UUID] | None = None) -> None:
        row = await self.repo.get_owned(invocation_id, user_id, tenant_id=tenant_id,
                                        tenant_ids=tenant_ids, lock=True)
        if row is None:
            raise NotFoundError("Shadow invocation")
        if row.status not in {"completed", "failed"}:
            raise ConflictError("Shadow invocation is not ready")
        await self.repo.acknowledge(row)
        await self.session.commit()
