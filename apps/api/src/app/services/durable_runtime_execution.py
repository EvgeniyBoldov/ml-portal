"""Execute a claimed segment through the normal chat pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.agents.runtime.confirmation import get_confirmation_service
from app.core.db import get_session_factory
from app.models.chat import Chats
from app.models.chat_turn import ChatTurn
from app.models.durable_runtime import DurableRuntimeRun
from app.models.user import Users
from app.repositories.api_tokens_repo import ApiTokensRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.runtime.interaction import interaction_from_context
from app.schemas.runtime_continuation import RuntimeResumeRequest
from app.services.chat_stream_service import ChatStreamService
from app.services.durable_runtime_service import (
    DURABLE_CHECKPOINT_VERSION,
    DurableRuntimeClaim,
    DurableRuntimeService,
)
from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService


class DurableClaimLost(RuntimeError):
    """The segment no longer belongs to this executor."""


class DurableExecutionSegment:
    def __init__(self, session: AsyncSession, claim: DurableRuntimeClaim) -> None:
        self.service = DurableRuntimeService(session)
        self.claim = claim
        self.finished = False

    async def fence(self) -> None:
        if await self.service.fence_claim(self.claim.segment_id, self.claim.claim_id) is None:
            raise DurableClaimLost("Durable runtime claim was superseded")

    async def fence_effect(self) -> None:
        async with get_session_factory()() as session:
            await DurableExecutionSegment(session, self.claim).fence()

    async def finish(
        self,
        status: str,
        *,
        context: dict[str, Any] | None = None,
        action: dict[str, Any] | None = None,
        public_payload: dict[str, Any] | None = None,
    ) -> None:
        wake_at = None
        pause_id = UUID(str(context["pause_id"])) if context and context.get("pause_id") else None
        if status == "waiting_timer":
            if context is None or pause_id is None:
                raise ValueError("Durable timer pause requires its planner pause ID")
            wake_at = datetime.fromisoformat(context["wake_at"])
            public_payload = (
                {"pause_id": str(pause_id), "content": context["user_update"], "wake_at": context["wake_at"]}
                if context.get("user_update") else None
            )
        elif status in {"waiting_input", "waiting_confirmation"}:
            interaction = interaction_from_context(context)
            if interaction is None:
                raise ValueError("Durable user pause requires a typed interaction")
            public_payload = {
                "pause_id": interaction.id,
                "content": interaction.question,
                "interaction": interaction.public(),
            }

        await self.service.complete_segment(
            self.claim, status=status, context=context, action=action,
            wake_at=wake_at, pause_id=pause_id, public_payload=public_payload,
        )
        self.finished = True


async def _build_execution_input(
    session: AsyncSession,
    claim: DurableRuntimeClaim,
    turn: ChatTurn,
    tenant_id: UUID,
    original_request: str,
) -> tuple[str, dict[str, Any], list[str]]:
    meta: dict[str, Any] = {"durable_runtime": True}
    checkpoint_service = RuntimeResumeCheckpointService.from_session(session)
    if not claim.context or not claim.context.get("resume"):
        if claim.attempt > 1:
            goal = await checkpoint_service.resolve_original_goal(claim.run_id)
            if goal:
                meta.update(
                    resumed_from_run_id=str(claim.run_id),
                    resume_checkpoint=checkpoint_service.build(
                        run_id=claim.run_id, agent_slug="", tenant_id=tenant_id, user_id=turn.user_id,
                        chat_id=turn.chat_id, paused_action=None, paused_context=None,
                        resume_action="segment_recovered",
                        source_context_snapshot={"inputs": {"goal": goal, "user_request": original_request}},
                    ),
                )
        return original_request, meta, []

    if claim.context.get("version", 1) != DURABLE_CHECKPOINT_VERSION:
        raise ValueError("Unsupported durable runtime checkpoint version")
    resume = claim.context["resume"]
    context = claim.context["context"]
    paused_action = claim.context.get("action")
    goal = await checkpoint_service.resolve_original_goal(claim.run_id)
    goal = goal or context.get("original_goal") or original_request
    timer = resume["signal_type"] == "timer_elapsed"
    tokens: list[str] = []
    if timer:
        action, content, response = "timer_elapsed", original_request, None
    else:
        resolved, content, response = checkpoint_service.resolve_request(
            RuntimeResumeRequest(action="answer", pause_id=str(resume["pause_id"]), response=resume["payload"]["response"]),
            context,
        )
        action = resolved.value
        interaction = interaction_from_context(context)
        operation = interaction.operation if interaction else None
        fingerprint = (operation or {}).get("operation_fingerprint")
        if response is True and fingerprint:
            token, _ = get_confirmation_service().issue(
                fingerprint=fingerprint, user_id=turn.user_id, chat_id=turn.chat_id,
            )
            tokens.append(token)

    checkpoint = checkpoint_service.build(
        run_id=claim.run_id, agent_slug="", tenant_id=tenant_id, user_id=turn.user_id,
        chat_id=turn.chat_id, paused_action=paused_action, paused_context=context,
        resume_action=action, user_input=None if timer else content,
        source_context_snapshot={"inputs": {"goal": goal, "user_request": original_request}},
    )
    if timer:
        checkpoint.update(
            pause_id=str(resume["pause_id"]),
            planned_wake_at=context["wake_at"],
            actual_wake_at=resume["received_at"],
        )
    else:
        checkpoint["interaction_response"] = response
    meta.update(resume_checkpoint=checkpoint, resumed_from_run_id=str(claim.run_id))
    return content, meta, tokens


async def execute_claimed_segment(
    claim: DurableRuntimeClaim,
    *,
    session: AsyncSession,
    llm_client: LLMClientProtocol,
    redis_client: Any,
) -> None:
    segment = DurableExecutionSegment(session, claim)
    run = await session.get(DurableRuntimeRun, claim.run_id)
    turn = await session.get(ChatTurn, claim.chat_turn_id)
    if run is None or turn is None:
        raise DurableClaimLost("Durable runtime run no longer exists")

    tenant_id = UUID(str(run.request_payload["tenant_id"]))
    user = await session.get(Users, turn.user_id)
    chat = await session.get(Chats, turn.chat_id)
    memberships = await ApiTokensRepository(session).active_tenant_ids(turn.user_id)
    if user is None or not user.is_enabled or chat is None or chat.owner_id != turn.user_id or str(tenant_id) not in memberships:
        await segment.finish("failed", public_payload={"content": "Доступ к поручению больше недоступен."})
        await session.commit()
        return

    content, meta, tokens = await _build_execution_input(
        session, claim, turn, tenant_id, str(run.request_payload["content"]),
    )
    if timezone := run.request_payload.get("timezone"):
        meta["durable_timezone"] = timezone
    if referenced_context := run.request_payload.get("referenced_context"):
        meta["durable_reference_context"] = referenced_context
    chat_id, user_id, turn_id = turn.chat_id, turn.user_id, turn.id
    # Release the connection before pipeline preparation starts.
    await session.commit()
    await segment.fence_effect()

    repositories = AsyncRepositoryFactory(session, tenant_id, user_id)
    stream_service = ChatStreamService(
        session=session, redis=redis_client, llm_client=llm_client,
        chats_repo=repositories.get_chats_repository(),
        messages_repo=repositories.get_chat_messages_repository(),
    )
    async for _ in stream_service.send_message_stream(
        chat_id=str(chat_id), user_id=str(user_id), tenant_id=str(tenant_id),
        content=content, confirmation_tokens=tokens, continuation_meta=meta,
        resumed_turn_id=str(turn_id), persist_user_message=False,
        runtime_run_id=str(claim.run_id), durable_segment=segment,
    ):
        pass
    if not segment.finished:
        raise RuntimeError("Chat pipeline ended without a persisted durable outcome")
