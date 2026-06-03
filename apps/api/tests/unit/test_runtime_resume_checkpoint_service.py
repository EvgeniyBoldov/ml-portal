from uuid import uuid4

from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService


def test_build_resume_checkpoint_payload_contains_required_fields():
    run_id = uuid4()
    payload = RuntimeResumeCheckpointService().build(
        run_id=run_id,
        agent_slug="ops-agent",
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=uuid4(),
        paused_action={"type": "resume"},
        paused_context={"reason": "waiting_input"},
        resume_action="input",
        user_input="hello",
    )

    assert payload["source_run_id"] == str(run_id)
    assert payload["agent_slug"] == "ops-agent"
    assert payload["resume_action"] == "input"
    assert payload["user_input"] == "hello"
    assert payload["checkpoint_id"]
    assert payload["created_at"]


def test_build_resume_checkpoint_payload_carries_source_goal_snapshot():
    payload = RuntimeResumeCheckpointService().build(
        run_id=uuid4(),
        agent_slug="ops-agent",
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=uuid4(),
        paused_action={"type": "resume"},
        paused_context={"reason": "waiting_confirmation"},
        resume_action="confirm",
        source_context_snapshot={
            "inputs": {
                "user_request": "Покажи коллекции",
                "goal": "Покажи коллекции",
            },
            "meta": {"model": "llama"},
        },
    )

    assert payload["original_goal"] == "Покажи коллекции"
    assert payload["original_user_request"] == "Покажи коллекции"
    assert payload["source_context_snapshot"]["inputs"]["goal"] == "Покажи коллекции"
