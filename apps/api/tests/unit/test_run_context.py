from types import SimpleNamespace
from uuid import uuid4

from app.agents.context import ToolContext
from app.runtime.artifact_visibility import branch_visible_artifacts
from app.runtime.run_context import RunContext


def test_evidence_selection_preserves_provenance_and_scope_without_mutating_original():
    context = RunContext(original_request="Compare", constraints=["Use the supplied file"])
    first = context.add_evidence("memory.search", {"query": "rules"}, {"groups": [
        {"scope_slug": "a", "success": True, "items": [{"text": "A"}]},
        {"scope_slug": "b", "success": False, "items": []}]})
    context.add_evidence("file.read", {"artifact_id": "file"}, {"content": "file data", "truncated": True})
    projection = context.projection(scope_keys=["a"], evidence_refs=[first])
    assert len(projection["evidence"]) == 1
    assert projection["evidence"][0]["owner"] == "turn_preflight"
    assert projection["evidence"][0]["data"]["groups"] == [{"scope_slug": "a", "success": True, "items": [{"text": "A"}]}]
    assert len(context.evidence[0].data["groups"]) == 2
    assert RunContext.model_validate_json(context.model_dump_json()).constraints == context.constraints


def test_sandbox_visibility_uses_frozen_inputs_and_branch_observations():
    context = RunContext(available_artifact_ids=["observed"], generated_artifacts=[{"artifact_id": "generated"}])
    state = SimpleNamespace(attachment_contexts=[SimpleNamespace(ref=SimpleNamespace(artifact_id="input"))], run_context=context)
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"runtime_branch_id": "branch", "runtime_turn_state": state})
    assert branch_visible_artifacts(ctx) == {"input", "observed", "generated"}
    ctx.extra.pop("runtime_turn_state")
    assert branch_visible_artifacts(ctx) == set()
    ctx.extra.pop("runtime_branch_id")
    assert branch_visible_artifacts(ctx) is None


def test_unrelated_history_does_not_overwrite_artifact_read_metadata():
    from app.runtime.context_outcome import RuntimeOutcomeProjector
    from app.runtime.turn_state import RuntimeTurnState
    state = RuntimeTurnState(run_id=uuid4(), attachment_contexts=[
        {"ref": {"artifact_id": "historical", "file_name": "old.txt"}},
        {"ref": {"artifact_id": "current", "file_name": "new.txt"}, "is_current": True}])
    state.run_context.add_evidence("file.read", {"artifact_id": "current"}, {
        "artifact_id": "current", "representation_id": "representation", "truncated": True})
    state.run_context.delivered_artifacts = [{"artifact_id": "current", "file_name": "new.txt"}]
    result = RuntimeOutcomeProjector.project(runtime_state=state, chat_id=str(uuid4()),
        chat_turn_id=str(uuid4()), terminal_state="completed")
    assert len(result.artifacts) == 1
    assert result.artifacts[0]["artifact_id"] == "current"
    assert result.artifacts[0]["file_name"] == "new.txt"
    assert result.artifacts[0]["representation_id"] == "representation"
    assert result.artifacts[0]["truncated"]


def test_history_cursor_has_a_json_wire_representation():
    from app.runtime.memory.role_tools import MemoryToolCall
    cursor = uuid4()
    call = MemoryToolCall(tool="chat.history.read", arguments={"before_message_id": cursor, "limit": 2})
    assert call.arguments.model_dump(mode="json")["before_message_id"] == str(cursor)
