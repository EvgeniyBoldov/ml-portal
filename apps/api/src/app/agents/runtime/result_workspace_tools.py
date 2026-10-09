"""Native, Pydantic-derived tools for a run's temporary data workspace."""
from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.context import ToolCall, ToolContext, ToolResult
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.core.config import get_settings
from app.services.result_workspace import ResultWorkspace
from app.services.tool_result_store import ToolResultStore, ToolResultStoreError


class DescribeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str


class SchemaArgs(DescribeArgs):
    offset: int = Field(default=0, ge=0, description="Schema page offset, from next_schema_offset.")
    limit: int = Field(default=20, ge=1, le=100)
    query: str = Field(default="", description="Comma-separated search terms for top-level column names; does not filter records.")


class ReadArgs(DescribeArgs):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    fields: list[str] = Field(default_factory=list, description="Exact top-level sql_columns names from result.describe. Nested values remain JSONB. Omit to read whole records.")
    revision: int | None = Field(default=None, ge=1)


class LoadArgs(DescribeArgs):
    mode: str = Field(default="next", pattern="^(next|remaining)$")
    max_pages: int | None = Field(default=None, ge=1, le=100)


class SQLArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1)


class AggregateArgs(DescribeArgs):
    columns: list[str] = Field(min_length=1, description="Top-level columns to group by; returns a count for each combination.")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class FindArgs(DescribeArgs):
    q: str = Field(min_length=1, description="Literal case-insensitive text searched across each saved JSON record.")
    columns: list[str] = Field(default_factory=list, description="Optional top-level columns to return.")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


WORKSPACE_TOOLS = {
    "result.describe": (SchemaArgs, "Read the actual SQL column schema of a saved dataset, revision and source state. Use exact sql_columns names in result.sql or result.read. Continue with next_schema_offset or query to find a field."),
    "result.read": (ReadArgs, "Read a bounded page of saved records. This does not fetch from the source. Use next_offset and revision to continue; select fields for large records."),
    "result.load": (LoadArgs, "Fetch the next source page or remaining pages within a budget into the same dataset. Rechecks source operation permissions; does not read records into context."),
    "result.aggregate": (AggregateArgs, "Group saved rows by top-level columns and count each combination. Uses the same virtual SQL table; saves the query output. Does not fetch source pages."),
    "result.find": (FindArgs, "Find saved rows containing literal text, including nested JSONB values. Uses the same virtual SQL table; saves the query output. Does not fetch source pages."),
    "result.sql": (SQLArgs, "Run one PostgreSQL SELECT over saved result_<uuid> tables. Columns are exactly the top-level sql_columns from result.describe. There are no added storage columns. Object/array columns are JSONB; scalar columns are typed. Filter, aggregate or join; output is saved as a new dataset."),
}


def with_workspace_operations(operations: list[ResolvedOperation]) -> list[ResolvedOperation]:
    if not operations:
        return operations
    result = list(operations)
    known = {operation.operation_slug for operation in result}
    for name, (model, description) in WORKSPACE_TOOLS.items():
        if name in known:
            continue
        if name in {"result.sql", "result.aggregate", "result.find"} and not any("result.analyze" in item.operation_slug for item in operations):
            continue
        result.append(ResolvedOperation(
            operation_slug=name, operation=name, name=name, scope="system",
            description=description, input_schema=model.model_json_schema(),
            data_instance_id="runtime-workspace", data_instance_slug="runtime-workspace",
            source="local", idempotent=name != "result.load", raw_tool_slug=name,
            target=ProviderExecutionTarget(operation_slug=name, provider_type="local", handler_slug=name,
                data_instance_id="runtime-workspace", data_instance_slug="runtime-workspace"),
        ))
    return result


async def execute_workspace(call: ToolCall, ctx: ToolContext, facade: Any,
                            operations: list[ResolvedOperation], timeout_s: float | None) -> ToolResult:
    model = WORKSPACE_TOOLS[call.tool_name][0]
    args = model.model_validate(call.arguments).model_dump()
    run_id = str(ctx.extra.get("runtime_root_run_id") or "")
    if not run_id:
        return ToolResult.fail("Workspace requires an active runtime run", workspace_view=True)
    scope = {"run_id": run_id, "tenant_id": ctx.tenant_id, "user_id": ctx.user_id}
    workspace = ResultWorkspace()
    try:
        if call.tool_name == "result.sql":
            data = await ToolResultStore().execute_sql(sql=args["sql"], call_id=call.id,
                task_id=str(ctx.extra.get("runtime_task_id") or "") or None,
                agent_execution_id=str(ctx.extra.get("run_id") or "") or None, **scope)
            saved = data.pop("_stored_result")
            return ToolResult.ok(data, stored_result=saved, workspace_view=True)
        scope["result_id"] = args.pop("result_id")
        if call.tool_name in {"result.aggregate", "result.find"}:
            data = await workspace.standard_query(kind=call.tool_name.split(".")[1], **args, **scope,
                call_id=call.id, task_id=str(ctx.extra.get("runtime_task_id") or "") or None,
                agent_execution_id=str(ctx.extra.get("run_id") or "") or None)
            saved = data.pop("_stored_result")
            return ToolResult.ok(data, stored_result=saved, workspace_view=True)
        if call.tool_name == "result.describe":
            data = await workspace.describe(**args, **scope)
        elif call.tool_name == "result.read":
            data = await workspace.read(**args, **scope)
        else:
            async def load() -> dict[str, Any]:
                settings = get_settings()
                max_pages = min(args["max_pages"] or settings.TOOL_RESULTS_LOAD_MAX_PAGES,
                                settings.TOOL_RESULTS_LOAD_MAX_PAGES)
                if args["mode"] == "next":
                    max_pages = 1
                pages = 0
                error = None
                while pages < max_pages:
                    state = await workspace.state(**scope)
                    meta = state["dataset_meta"]
                    next_arguments = meta.get("next_arguments")
                    if not next_arguments:
                        if meta.get("has_next"):
                            error = "Source adapter did not publish executable continuation arguments"
                        break
                    operation, _ = facade._find_operation(state["operation"], next_arguments, operations)
                    if not operation or operation.side_effects or operation.risk_level != "safe":
                        raise ToolResultStoreError("Source continuation operation is unavailable or not read-only")
                    page_call = ToolCall(id=f"{call.id}.page{state['revision']}",
                        tool_name=operation.operation_slug, arguments=next_arguments)
                    previous_reuse = ctx.extra.get("runtime_tool_reuse_enabled", True)
                    ctx.extra["runtime_tool_reuse_enabled"] = False
                    try:
                        result, _ = await facade.execute(page_call, ctx, operations, timeout_s=timeout_s)
                    finally:
                        ctx.extra["runtime_tool_reuse_enabled"] = previous_reuse
                    if not result.success:
                        error = result.error
                        break
                    from app.runtime.redactor import RuntimeRedactor
                    await workspace.append_page(payload=RuntimeRedactor().redact(result.data), source_tool=meta["source_tool"],
                        arguments=next_arguments, expected_revision=state["revision"], call_id=page_call.id, **scope)
                    pages += 1
                return {**await workspace.describe(**scope), "pages_loaded": pages,
                        "load_error": error, "budget_reached": pages == max_pages and bool((await workspace.state(**scope))["dataset_meta"].get("has_next"))}
            try:
                data = await asyncio.wait_for(load(), timeout=min(timeout_s or get_settings().TOOL_RESULTS_LOAD_TIMEOUT_SECONDS,
                    get_settings().TOOL_RESULTS_LOAD_TIMEOUT_SECONDS))
            except (TimeoutError, ToolResultStoreError) as exc:
                data = {**await workspace.describe(**scope), "load_error": str(exc) or "Loading time budget reached"}
        return ToolResult.ok(data, workspace_view=True)
    except ToolResultStoreError as exc:
        return ToolResult.fail(str(exc), workspace_view=True)
