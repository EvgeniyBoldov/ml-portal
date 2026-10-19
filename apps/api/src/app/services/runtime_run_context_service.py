from __future__ import annotations

import uuid
from io import BytesIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.models.runtime_context import RuntimeRunContext
from app.runtime.run_context import RunContext
from app.repositories.runtime_run_context_repository import RuntimeRunContextRepository


class RuntimeRunContextService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = RuntimeRunContextRepository(session)

    async def load(self, *, run_id: str, chat_id: str, owner_id: str, branch_id: str | None, tenant_id: str | None = None) -> RunContext | None:
        row = await self.repository.owned(run_id=run_id, chat_id=chat_id, owner_id=owner_id, branch_id=branch_id)
        if row is None:
            return None
        payload = await s3_manager.get_object(row.manifest["bucket"], row.manifest["key"])
        if payload is None:
            raise ValueError("Saved run context is unavailable")
        context = RunContext.model_validate_json(payload)
        from app.services.chat_artifact_reference_service import ChatArtifactReferenceService, ChatArtifactReferenceError
        retained = []
        for evidence in context.evidence:
            if evidence.tool == "file.read":
                try:
                    await ChatArtifactReferenceService(self.session).resolve(
                        artifact_id=evidence.data["artifact_id"], chat_id=chat_id,
                        owner_id=owner_id, tenant_id=tenant_id)
                except ChatArtifactReferenceError:
                    continue
            retained.append(evidence)
        context.evidence = retained
        return context

    async def save(self, *, run_id: str, chat_id: str, owner_id: str,
                   branch_id: str | None, context: RunContext) -> None:
        row = await self.repository.get(run_id)
        if row and (str(row.chat_id) != chat_id or str(row.owner_id) != owner_id or row.branch_id != branch_id):
            raise ValueError("Run context identity mismatch")
        revision = (row.revision if row else 0) + 1
        bucket = get_settings().S3_BUCKET_CHAT_UPLOADS
        key = f"runtime-context/{chat_id}/{run_id}/{revision}-{uuid.uuid4()}.json"
        context.revision = revision
        if not await s3_manager.upload_fileobj(bucket, key, BytesIO(context.model_dump_json().encode())):
            raise ValueError("Could not save run context")
        if row is None:
            row = RuntimeRunContext(id=uuid.UUID(run_id), chat_id=uuid.UUID(chat_id),
                owner_id=uuid.UUID(owner_id), branch_id=branch_id)
            self.session.add(row)
        row.revision = revision
        row.manifest = {"bucket": bucket, "key": key, "evidence_ids": [item.id for item in context.evidence],
                        "artifact_ids": [item["artifact_id"] for item in context.generated_artifacts]}
        await self.session.flush()
