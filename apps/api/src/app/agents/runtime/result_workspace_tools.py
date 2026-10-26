"""Native, Pydantic-derived tools for a run's temporary data workspace."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.agents.context import ToolCall, ToolContext, ToolResult
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.core.config import get_settings
from app.services.result_workspace import ResultWorkspace
from app.services.tool_result_store import ToolResultStore, ToolResultStoreError

logger = logging.getLogger(__name__)


class DescribeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str


class SchemaArgs(DescribeArgs):
    offset: int = Field(default=0, ge=0, description="Schema page offset, from next_schema_offset.")
    limit: int = Field(default=20, ge=1, le=100)
    query: str = Field(default="", max_length=300, description="Comma-separated search terms for top-level column names; does not filter records.")


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
    sql: str = Field(min_length=1, description=(
        "Project only needed fields to reduce oversized records. For nested JSON use "
        "column->'object'->>'name': -> retains JSONB, ->> returns text and must be last. "
        "jsonb_object_keys(column) discovers object keys. SELECT column copies the same "
        "large object; saving it under a new result_id does not reduce its size."))


class AggregateArgs(DescribeArgs):
    columns: list[str] = Field(min_length=1, description="Top-level columns to group by; returns a count for each combination.")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    revision: int | None = Field(default=None, ge=1, description="Revision returned by the previous result.aggregate page.")


class FindArgs(DescribeArgs):
    q: str = Field(min_length=1, description="Literal case-insensitive text searched across each saved JSON record.")
    columns: list[str] = Field(default_factory=list, description="Optional top-level columns to return.")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    revision: int | None = Field(default=None, ge=1, description="Revision returned by the previous result.find page.")


WORKSPACE_TOOLS = {
    "result.describe": (SchemaArgs, "Read the actual SQL column schema of a saved dataset, revision and source state. Use exact sql_columns names in result.sql or result.read. Continue with next_schema_offset or query to find a field."),
    "result.read": (ReadArgs, "Read a bounded page of saved records. This does not fetch from the source. Use next_offset and revision to continue; select fields for large records."),
    "result.load": (LoadArgs, "Fetch the next source page or remaining pages within a budget into the same dataset. Rechecks source operation permissions; does not read records into context."),
    "result.aggregate": (AggregateArgs, "Group saved rows by top-level columns and count each combination. Uses the same virtual SQL table; saves the query output. Continue pages with the returned input_revision; a changed input revision requires restarting."),
    "result.find": (FindArgs, "Find saved rows containing literal case-insensitive text, including nested JSONB values. Continue pages with the returned input_revision; a changed input revision requires restarting."),
    "result.sql": (SQLArgs, "Run one PostgreSQL SELECT over saved result_<uuid> tables. Columns are exactly the top-level sql_columns from result.describe. There are no added storage columns. Object/array columns are JSONB; scalar columns are typed. Filter, aggregate or join; output is saved as a new dataset."),
}


def with_workspace_operations(operations: list[ResolvedOperation]) -> list[ResolvedOperation]:
    result = list(operations)
    known = {operation.operation_slug for operation in result}
    for name, (model, description) in WORKSPACE_TOOLS.items():
        if not operations and name not in {"result.describe", "result.read"}:
            continue
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
                            error = meta.get("continuation_error") or "Source adapter did not publish executable continuation arguments"
                        break
                    operation, _ = facade._find_operation(state["operation"], next_arguments, operations)
                    if not operation or operation.side_effects or operation.risk_level != "safe":
                        raise ToolResultStoreError("Source continuation operation is unavailable or not read-only")
                    call_budget = ctx.extra.get("runtime_tool_call_budget")
                    if isinstance(call_budget, tuple) and len(call_budget) == 2:
                        counter, limit = call_budget
                        if isinstance(counter, list) and counter and int(counter[0]) + 1 >= int(limit):
                            error = "Tool-call budget reached before fetching another source page"
                            break
                        if isinstance(counter, list) and counter:
                            counter[0] += 1
                    page_call = ToolCall(id=f"{call.id}.page{state['revision']}",
                        tool_name=operation.operation_slug, arguments=next_arguments)
                    ledger = ctx.extra.get("runtime_tool_ledger")
                    if ledger is not None and hasattr(ledger, "register_call"):
                        ledger.register_call(operation=page_call.tool_name, call_id=page_call.id,
                            arguments=page_call.arguments, iteration=0,
                            agent_slug=str(ctx.extra.get("runtime_agent_slug") or "") or None,
                            phase_id=str(ctx.extra.get("runtime_task_id") or "") or None)
                    previous_reuse = ctx.extra.get("runtime_tool_reuse_enabled", True)
                    ctx.extra["runtime_tool_reuse_enabled"] = False
                    try:
                        result, _ = await facade.execute(page_call, ctx, operations, timeout_s=timeout_s)
                    finally:
                        ctx.extra["runtime_tool_reuse_enabled"] = previous_reuse
                    if not result.success:
                        if ledger is not None and hasattr(ledger, "register_result"):
                            ledger.register_result(call_id=page_call.id, success=False,
                                data={"error": str(result.error or "Source page request failed")})
                        error = result.error
                        break
                    from app.runtime.redactor import RuntimeRedactor
                    appended = await workspace.append_page(payload=RuntimeRedactor().redact(result.data), source_tool=meta["source_tool"],
                        arguments=next_arguments, expected_revision=state["revision"], call_id=page_call.id, **scope)
                    if not appended.get("appended"):
                        if ledger is not None and hasattr(ledger, "register_result"):
                            ledger.register_result(call_id=page_call.id, success=False,
                                data={"error": "Source page did not advance the saved dataset"})
                        error = "Source page was already loaded; stopping to avoid a continuation cycle"
                        break
                    if ledger is not None and hasattr(ledger, "register_result"):
                        ledger.register_result(call_id=page_call.id, success=True,
                            data={"result_id": scope["result_id"], "revision": appended["revision"]},
                            result_id=scope["result_id"])
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
    except (SQLAlchemyError, TimeoutError) as exc:
        logger.exception("Runtime result workspace storage failure operation=%s", call.tool_name)
        return ToolResult.fail("Result workspace is temporarily unavailable; retry the read or load operation.",
                               workspace_view=True, error_code="result_workspace_unavailable")
