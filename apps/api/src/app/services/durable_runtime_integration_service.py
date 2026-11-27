"""Transactional admission and reply workflows for external chat adapters."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessages, Chats
from app.models.chat_turn import ChatTurn
from app.models.durable_runtime import DurableRuntimePause, DurableRuntimeRun
from app.schemas.durable_runtime import AcceptedRun, AdmitRunRequest
from app.schemas.runtime_continuation import RuntimeResumeAction, RuntimeResumeRequest
from app.services.chat_turn_service import ChatTurnService
from app.services.durable_runtime_service import DurableRuntimeConflict, DurableRuntimeService
from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService, RuntimeResumeValidationError


class DurableRuntimeIntegrationError(ValueError):
    """Base error for invalid adapter workflow operations."""


class DurableRuntimeIntegrationNotFound(DurableRuntimeIntegrationError):
    """The run is not visible to this authenticated user."""


class DurableRuntimeIntegrationConflict(DurableRuntimeIntegrationError):
    """The event or lifecycle state conflicts with an accepted operation."""


class DurableRuntimeIntegrationInvalidResponse(DurableRuntimeIntegrationError):
    """The response does not match the active interaction schema."""


def integration_event_key(user_id: UUID, integration_id: str, event_id: str, workspace_id: str = "") -> str:
    raw = f"{user_id}:{integration_id}:{workspace_id}:{event_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class DurableRuntimeIntegrationService:
    """Use one caller-owned AsyncSession transaction for each adapter command."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = DurableRuntimeService(session)

    async def admit(
        self,
        body: AdmitRunRequest,
        *,
        owner_user_id: UUID,
        tenant_id: UUID,
        connector_context: dict[str, Any] | None = None,
    ) -> AcceptedRun:
        admission_key = integration_event_key(
            owner_user_id, body.address.integration_id, body.event_id, body.address.workspace_id,
        )
        await self.runs.lock_admission_key(admission_key)
        existing = await self.runs.get_run_by_admission_key(admission_key)
        expected_recipient = body.address.model_dump()
        if connector_context is not None:
            expected_recipient["assignment"] = connector_context
        if existing is not None:
            if (existing.request_payload.get("content") != body.text
                    or existing.request_payload.get("timezone") != body.timezone
                    or existing.request_payload.get("referenced_context") != body.referenced_context
                    or existing.recipient != expected_recipient):
                raise DurableRuntimeIntegrationConflict("Event ID was already used with different content")
            turn = await self.session.get(ChatTurn, existing.chat_turn_id)
            if turn is None:
                raise DurableRuntimeIntegrationConflict("The accepted run is incomplete")
            return AcceptedRun(chat_id=turn.chat_id, run_id=existing.id, event_id=body.event_id,
                               status=existing.status)

        chat_id, root_run_id, message_id = uuid4(), uuid4(), uuid4()
        self.session.add(Chats(id=chat_id, owner_id=owner_user_id, name="Background task", tags=["durable-runtime"]))
        await self.session.flush()
        self.session.add(ChatMessages(
            id=message_id,
            chat_id=chat_id,
            role="user",
            content={"text": body.text},
            message_type="text",
            meta={"source": "integration", "event_id": body.event_id,
                  "integration_id": body.address.integration_id},
        ))
        await self.session.flush()
        turn_service = ChatTurnService(self.session)
        turn = await turn_service.start_turn(
            chat_id=chat_id,
            user_id=owner_user_id,
            tenant_id=tenant_id,
            idempotency_key=admission_key,
            request_hash=turn_service.build_request_hash(body.text),
            runtime_run_id=root_run_id,
        )
        turn.status = "queued"
        await turn_service.attach_user_message(turn.id, message_id)
        run = await self.runs.create_run(
            chat_turn_id=turn.id,
            owner_user_id=owner_user_id,
            request_payload={
                "content": body.text,
                "tenant_id": str(tenant_id),
                "timezone": body.timezone,
                "referenced_context": body.referenced_context,
                "source_message_id": body.address.source_message_id,
                "event_id": body.event_id,
                "integration_id": body.address.integration_id,
            },
            idempotency_key=admission_key,
            admission_key=admission_key,
            recipient=expected_recipient,
            root_run_id=root_run_id,
        )
        return AcceptedRun(chat_id=chat_id, run_id=run.id, event_id=body.event_id)

    async def respond(
        self,
        run_id: UUID,
        *,
        owner_user_id: UUID,
        event_id: str,
        pause_id: UUID,
        value: str | bool,
    ) -> dict[str, Any]:
        # The row lock serializes answers for this run before duplicate lookup
        # and message insertion, so parallel delivery cannot write twice.
        run = await self.session.scalar(
            select(DurableRuntimeRun).where(DurableRuntimeRun.id == run_id).with_for_update()
        )
        if run is None or run.owner_user_id != owner_user_id:
            raise DurableRuntimeIntegrationNotFound("Run not found")
        turn = await self.session.get(ChatTurn, run.chat_turn_id)
        if turn is None:
            raise DurableRuntimeIntegrationNotFound("Run not found")

        recipient = run.recipient or {}
        event_key = integration_event_key(
            owner_user_id, str(recipient.get("integration_id", "")), event_id,
            str(recipient.get("workspace_id", "")),
        )
        prior = await self.runs.get_command(run_id, event_key)
        if prior is not None:
            if prior.payload.get("response") != value or prior.payload.get("pause_id") != str(pause_id):
                raise DurableRuntimeIntegrationConflict("Event ID was already used with different content")
            return {"run_id": str(run.id), "status": run.status, "accepted": True}

        pause = await self.session.scalar(select(DurableRuntimePause).where(
            DurableRuntimePause.run_id == run_id,
            DurableRuntimePause.status == "active",
        ).with_for_update())
        if pause is None or pause.id != pause_id:
            raise DurableRuntimeIntegrationConflict("There is no matching active pause")
        try:
            RuntimeResumeCheckpointService.resolve_request(
                RuntimeResumeRequest(action=RuntimeResumeAction.ANSWER, pause_id=str(pause_id), response=value),
                (pause.payload or {}).get("context"),
            )
        except RuntimeResumeValidationError as exc:
            raise DurableRuntimeIntegrationInvalidResponse(str(exc)) from exc

        message_id = uuid4()
        response_text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        self.session.add(ChatMessages(
            id=message_id,
            chat_id=turn.chat_id,
            role="user",
            content={"text": response_text},
            message_type="text",
            meta={"source": "integration_response", "run_id": str(run_id),
                  "pause_id": str(pause_id), "event_id": event_id},
        ))
        await self.session.flush()
        try:
            updated = await self.runs.accept_signal(
                run_id,
                event_key=event_key,
                signal_type="answer",
                payload={"response": value, "pause_id": str(pause_id), "message_id": str(message_id),
                         "received_at": datetime.now(timezone.utc).isoformat()},
                pause_id=pause_id,
                actor_user_id=owner_user_id,
            )
        except DurableRuntimeConflict as exc:
            raise DurableRuntimeIntegrationConflict(str(exc)) from exc
        return {"run_id": str(updated.id), "status": updated.status, "accepted": True}
