from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.sandbox import runs as sandbox_runs
from app.schemas.sandbox import SandboxRunCreate
from app.schemas.runtime_continuation import RuntimeResumeAction, RuntimeResumeRequest
from app.services.sandbox.turn_lifecycle import SandboxTurnLifecycleService


@pytest.mark.asyncio
async def test_setup_failure_terminalizes_existing_hidden_sandbox_turn() -> None:
    turn = SimpleNamespace(id=uuid4())
    turns = AsyncMock()
    turns.get_by_runtime_run_id = AsyncMock(return_value=turn)
    sandbox = AsyncMock()

    with (
        patch("app.services.sandbox.turn_lifecycle.ChatTurnService", return_value=turns),
        patch("app.services.sandbox.turn_lifecycle.SandboxService", return_value=sandbox),
    ):
        await SandboxTurnLifecycleService(AsyncMock()).fail_setup(
            run_id=uuid4(), error="agent resolution failed",
        )

    sandbox.finish_run.assert_awaited_once()
    turns.fail_turn.assert_awaited_once_with(turn.id, error_message="agent resolution failed")


@pytest.mark.asyncio
async def test_run_sandbox_cancellation_during_attachment_setup_terminalizes_committed_run() -> None:
    session_id, branch_id, run_id = uuid4(), uuid4(), uuid4()
    user_id, tenant_id, chat_id = uuid4(), uuid4(), uuid4()
    db = AsyncMock()
    service = MagicMock()
    service.get_session = AsyncMock(return_value=SimpleNamespace(status="active"))
    service.get_branch = AsyncMock(return_value=SimpleNamespace(id=branch_id, session_id=session_id))
    service.prepare_run = AsyncMock(return_value=SimpleNamespace(
        run=SimpleNamespace(id=run_id), snapshot=SimpleNamespace(id=uuid4()), effective_config={},
    ))
    attachment_service = MagicMock()
    attachment_service.build_runtime_artifact_contexts = AsyncMock(side_effect=asyncio.CancelledError())

    with (
        patch("app.api.v1.routers.sandbox.runs.SandboxService", return_value=service),
        patch("app.api.v1.routers.sandbox.runs.check_session_owner", new_callable=AsyncMock),
        patch("app.api.v1.routers.sandbox.runs.user_uuid", return_value=user_id),
        patch("app.api.v1.routers.sandbox.runs.tenant_uuid", new_callable=AsyncMock, return_value=tenant_id),
        patch("app.api.v1.routers.sandbox.runs.get_session_factory", return_value=object()),
        patch("app.api.v1.routers.sandbox.runs._ensure_sandbox_upload_chat", new_callable=AsyncMock, return_value=chat_id),
        patch("app.api.v1.routers.sandbox.runs.ChatAttachmentService", return_value=attachment_service),
        patch("app.api.v1.routers.sandbox.runs._fail_sandbox_setup", new_callable=AsyncMock) as fail_setup,
    ):
        with pytest.raises(asyncio.CancelledError):
            await sandbox_runs.run_sandbox(
                session_id=session_id,
                data=SandboxRunCreate(
                    request_text="probe", branch_id=branch_id, artifact_ids=[uuid4()],
                ),
                db=db,
                user=SimpleNamespace(),
                llm_client=AsyncMock(),
            )

    fail_setup.assert_awaited_once()
    assert fail_setup.await_args.kwargs["run_id"] == run_id
    assert fail_setup.await_args.kwargs["stream_db"] is db
    assert db.commit.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("action", [RuntimeResumeAction.INPUT, RuntimeResumeAction.CANCEL])
async def test_resume_claim_loser_gets_409_without_terminalizing_live_owner(action) -> None:
    session_id, run_id = uuid4(), uuid4()
    user_id, tenant_id, chat_id, branch_id = uuid4(), uuid4(), uuid4(), uuid4()
    run = SimpleNamespace(
        id=run_id,
        session_id=session_id,
        status="waiting_input",
        paused_action={"kind": "input"},
        paused_context={"question": "original checkpoint"},
        effective_config={},
        branch_id=branch_id,
        request_text="request",
        input_artifact_ids=[],
    )
    db = AsyncMock()
    service = MagicMock()
    service.get_run = AsyncMock(return_value=run)
    service.get_branch = AsyncMock(return_value=SimpleNamespace(id=branch_id))
    service.resume_run = AsyncMock()
    service.finish_run = AsyncMock()
    service.claim_resume_run = AsyncMock(return_value=False)
    attachment_service = MagicMock()
    attachment_service.build_runtime_artifact_contexts = AsyncMock(return_value=[])
    resolver = MagicMock()
    resolver.sandbox_agent_slug.return_value = None
    resolver.sandbox_agent_version_id.return_value = None
    checkpoint_service = MagicMock()
    checkpoint_service.build.return_value = {}

    with (
        patch("app.api.v1.routers.sandbox.runs.SandboxService", return_value=service),
        patch("app.api.v1.routers.sandbox.runs.check_session_owner", new_callable=AsyncMock),
        patch("app.api.v1.routers.sandbox.runs.user_uuid", return_value=user_id),
        patch("app.api.v1.routers.sandbox.runs.tenant_uuid", new_callable=AsyncMock, return_value=tenant_id),
        patch("app.api.v1.routers.sandbox.runs._ensure_sandbox_upload_chat", new_callable=AsyncMock, return_value=chat_id),
        patch("app.api.v1.routers.sandbox.runs.ChatAttachmentService", return_value=attachment_service),
        patch("app.api.v1.routers.sandbox.runs.RuntimeSandboxResolver", return_value=resolver),
        patch("app.api.v1.routers.sandbox.runs.RuntimeResumeCheckpointService", return_value=checkpoint_service) as checkpoint_class,
        patch("app.api.v1.routers.sandbox.runs.get_session_factory", return_value=object()),
        patch("app.api.v1.routers.sandbox.runs._fail_sandbox_setup", new_callable=AsyncMock) as fail_setup,
    ):
        checkpoint_class.source_context_snapshot.return_value = {}
        checkpoint_class.resolve_request.return_value = (action, "answer", None)
        checkpoint_class.validate_action.return_value = "answer"
        with pytest.raises(HTTPException) as raised:
            await sandbox_runs.resume_sandbox_run(
                session_id=session_id,
                run_id=run_id,
                data=RuntimeResumeRequest(
                    action=action,
                    input="answer" if action is RuntimeResumeAction.INPUT else None,
                ),
                db=db,
                user=SimpleNamespace(),
                llm_client=AsyncMock(),
            )
    assert isinstance(raised.value, HTTPException)
    assert raised.value.status_code == 409
    service.claim_resume_run.assert_awaited_once_with(
        run_id,
        expected_status="waiting_input",
        expected_paused_action={"kind": "input"},
        expected_paused_context={"question": "original checkpoint"},
    )
    db.rollback.assert_awaited_once()
    service.resume_run.assert_not_awaited()
    service.finish_run.assert_not_awaited()
    fail_setup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_error", [RuntimeError("commit failed"), asyncio.CancelledError()])
async def test_resume_claim_commit_failure_rolls_back_without_failing_run(commit_error) -> None:
    session_id, run_id = uuid4(), uuid4()
    user_id, tenant_id, chat_id, branch_id = uuid4(), uuid4(), uuid4(), uuid4()
    run = SimpleNamespace(
        id=run_id,
        session_id=session_id,
        status="waiting_input",
        paused_action={"kind": "input"},
        paused_context={"question": "checkpoint"},
        effective_config={},
        branch_id=branch_id,
        request_text="request",
        input_artifact_ids=[],
    )
    db = AsyncMock()
    db.commit.side_effect = [None, commit_error]
    service = MagicMock()
    service.get_run = AsyncMock(return_value=run)
    service.get_branch = AsyncMock(return_value=SimpleNamespace(id=branch_id))
    service.claim_resume_run = AsyncMock(return_value=True)
    attachment_service = MagicMock()
    attachment_service.build_runtime_artifact_contexts = AsyncMock(return_value=[])
    resolver = MagicMock()
    resolver.sandbox_agent_slug.return_value = None
    resolver.sandbox_agent_version_id.return_value = None
    checkpoint_service = MagicMock()
    checkpoint_service.build.return_value = {}

    with (
        patch("app.api.v1.routers.sandbox.runs.SandboxService", return_value=service),
        patch("app.api.v1.routers.sandbox.runs.check_session_owner", new_callable=AsyncMock),
        patch("app.api.v1.routers.sandbox.runs.user_uuid", return_value=user_id),
        patch("app.api.v1.routers.sandbox.runs.tenant_uuid", new_callable=AsyncMock, return_value=tenant_id),
        patch("app.api.v1.routers.sandbox.runs._ensure_sandbox_upload_chat", new_callable=AsyncMock, return_value=chat_id),
        patch("app.api.v1.routers.sandbox.runs.ChatAttachmentService", return_value=attachment_service),
        patch("app.api.v1.routers.sandbox.runs.RuntimeSandboxResolver", return_value=resolver),
        patch("app.api.v1.routers.sandbox.runs.RuntimeResumeCheckpointService", return_value=checkpoint_service) as checkpoint_class,
        patch("app.api.v1.routers.sandbox.runs.get_session_factory", return_value=object()),
        patch("app.api.v1.routers.sandbox.runs._fail_sandbox_setup", new_callable=AsyncMock) as fail_setup,
    ):
        checkpoint_class.source_context_snapshot.return_value = {}
        checkpoint_class.resolve_request.return_value = (RuntimeResumeAction.INPUT, "answer", None)
        checkpoint_class.validate_action.return_value = "answer"
        with pytest.raises(type(commit_error)) as raised:
            await sandbox_runs.resume_sandbox_run(
                session_id=session_id,
                run_id=run_id,
                data=RuntimeResumeRequest(action=RuntimeResumeAction.INPUT, input="answer"),
                db=db,
                user=SimpleNamespace(),
                llm_client=AsyncMock(),
            )

    assert raised.value is commit_error
    assert db.commit.await_count == 2
    db.rollback.assert_awaited_once()
    service.claim_resume_run.assert_awaited_once()
    fail_setup.assert_not_awaited()
