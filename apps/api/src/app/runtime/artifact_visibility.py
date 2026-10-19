"""A sandbox branch may use only its frozen inputs and observed artifacts."""
from app.agents.context import ToolContext


def branch_visible_artifacts(ctx: ToolContext) -> set[str] | None:
    branch = ctx.extra.get("runtime_branch_id") or ctx.extra.get("sandbox_branch_id") or (
        ctx.get_runtime_deps().sandbox_overrides or {}).get("sandbox_branch_id")
    if not branch:
        return None
    state = ctx.extra.get("runtime_turn_state")
    if state is None:
        return set()
    return {item.ref.artifact_id for item in state.attachment_contexts} | set(
        state.run_context.available_artifact_ids) | {
        item["artifact_id"] for item in state.run_context.generated_artifacts}
