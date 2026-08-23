"""Read-only glossary-assisted project memory tools."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.repositories.memory_lookup_repository import MemoryLookupRepository
from app.runtime.project_memory_candidates import ProjectMemoryCandidate
from app.services.memory_lookup_service import MemoryLookupService


_LOOKUP_INPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "terms": {"type": "array", "minItems": 1, "maxItems": 24, "items": {"type": "string", "minLength": 1, "maxLength": 160}},
        "project_keys": {"type": "array", "maxItems": 8, "items": {"type": "string", "minLength": 1, "maxLength": 120}},
    },
    "required": ["terms"],
}
_LOOKUP_OUTPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "glossary": {"type": "array"}, "expanded_terms": {"type": "array"},
        "projects": {"type": "array"}, "ambiguous_projects": {"type": "array"},
        "project_suggestions": {"type": "array"},
    },
    "required": ["glossary", "expanded_terms", "projects", "ambiguous_projects", "project_suggestions"],
}
_READ_INPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "projects": {
            "type": "array", "minItems": 1, "maxItems": 8,
            "items": {"type": "object", "additionalProperties": False, "properties": {
                "project_key": {"type": "string", "minLength": 1, "maxLength": 120},
                "keys": {"type": "array", "minItems": 1, "maxItems": 12, "items": {"type": "string", "minLength": 1, "maxLength": 200}},
            }, "required": ["project_key", "keys"]},
        },
    },
    "required": ["projects"],
}
_READ_OUTPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {"projects": {"type": "array"}}, "required": ["projects"],
}
_MARK_INPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "project_key": {"type": "string", "minLength": 1},
        "candidates": {"type": "array", "minItems": 1, "maxItems": 12, "items": {
            "type": "object", "additionalProperties": False, "properties": {
                "subject": {"type": "string", "minLength": 1},
                "value": {"type": "string", "minLength": 1},
                "evidence_call_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "aliases": {"type": "array", "items": {"type": "string"}},
            }, "required": ["subject", "value", "evidence_call_ids"],
        }},
    }, "required": ["project_key", "candidates"],
}
_MARK_OUTPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {"accepted": {"type": "integer"}, "rejected": {"type": "array"}},
    "required": ["accepted", "rejected"],
}


def _service(ctx: ToolContext) -> MemoryLookupService:
    # Kept in a helper to make the handler a thin LLM-facing adapter.
    return MemoryLookupService(MemoryLookupRepository(ctx.extra["memory_lookup_session"]))


async def _run_with_session(ctx: ToolContext, callback: Any) -> Any:
    session_factory = ctx.get_runtime_deps().session_factory
    if session_factory is None:
        from app.core.db import get_session_factory
        session_factory = get_session_factory()
    async with session_factory() as session:
        ctx.extra["memory_lookup_session"] = session
        try:
            return await callback(_service(ctx))
        finally:
            ctx.extra.pop("memory_lookup_session", None)


@register_tool
class MemoryLookupTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.lookup"
    tool_group: ClassVar[str] = "memory"
    domains: ClassVar[list[str]] = ["system", "memory"]
    name: ClassVar[str] = "Lookup Memory Terms"
    description: ClassVar[str] = "Resolve glossary aliases, projects, and relevant project-memory keys without reading values."

    @tool_version(version="1.0.0", input_schema=_LOOKUP_INPUT, output_schema=_LOOKUP_OUTPUT, description="Resolve terms and discover project memory keys")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        notes = ctx.tool_notes(self.tool_slug)
        terms = args.get("terms") or []
        if not terms:
            return ToolResult.fail("Missing 'terms' argument", logs=notes.entries_dict())
        try:
            data = await _run_with_session(ctx, lambda service: service.lookup(
                terms=terms, project_keys=args.get("project_keys"), user_id=ctx.user_id, tenant_id=ctx.tenant_id,
            ))
        except Exception:
            notes.error("Memory lookup failed")
            return ToolResult.fail("Memory lookup is temporarily unavailable", logs=notes.entries_dict())
        notes.info("Memory terms resolved", terms=len(terms), projects=len(data["projects"]))
        return ToolResult.ok(data=data, logs=notes.entries_dict())


@register_tool
class MemoryReadTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.read"
    tool_group: ClassVar[str] = "memory"
    domains: ClassVar[list[str]] = ["system", "memory"]
    name: ClassVar[str] = "Read Project Memory"
    description: ClassVar[str] = "Read confirmed values for project-memory keys returned by memory.lookup."

    @tool_version(version="1.0.0", input_schema=_READ_INPUT, output_schema=_READ_OUTPUT, description="Read bounded confirmed project-memory values")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        notes = ctx.tool_notes(self.tool_slug)
        projects = args.get("projects") or []
        if not projects:
            return ToolResult.fail("Missing 'projects' argument", logs=notes.entries_dict())
        try:
            data = await _run_with_session(ctx, lambda service: service.read(
                projects=projects, tenant_id=ctx.tenant_id,
            ))
        except Exception:
            notes.error("Project memory read failed")
            return ToolResult.fail("Project memory is temporarily unavailable", logs=notes.entries_dict())
        notes.info("Project memory read", projects=len(data["projects"]))
        return ToolResult.ok(data=data, logs=notes.entries_dict())


@register_tool
class MemoryMarkTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.mark"
    tool_group: ClassVar[str] = "memory"
    domains: ClassVar[list[str]] = ["system", "memory"]
    name: ClassVar[str] = "Mark Project Memory Candidates"
    description: ClassVar[str] = "Mark evidenced project knowledge for asynchronous review; this never writes durable memory."

    @tool_version(version="1.0.0", input_schema=_MARK_INPUT, output_schema=_MARK_OUTPUT, description="Mark evidenced project memory candidates in current run state")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        notes = ctx.tool_notes(self.tool_slug)
        state = ctx.extra.get("runtime_turn_state")
        ledger = ctx.extra.get("runtime_tool_ledger")
        if state is None or not hasattr(state, "project_memory_candidates") or ledger is None:
            return ToolResult.fail("Memory marking is available only during a runtime turn.", logs=notes.entries_dict())
        project_key = str(args.get("project_key") or "").strip().lower()
        if not project_key:
            return ToolResult.fail("Missing 'project_key' argument", logs=notes.entries_dict())
        valid_ids = {
            entry.call_id for entry in ledger.entries
            if entry.status == "succeeded" and entry.result_data is not None and entry.operation != self.tool_slug
        }
        rejected: list[dict[str, Any]] = []
        accepted = 0
        existing = {(item.project_key, item.subject, item.value) for item in state.project_memory_candidates}
        for index, raw in enumerate(args.get("candidates") or []):
            if not isinstance(raw, dict):
                rejected.append({"index": index, "reason": "invalid_candidate"})
                continue
            evidence_ids = [str(item).strip() for item in raw.get("evidence_call_ids") or [] if str(item).strip()]
            if not evidence_ids or any(item not in valid_ids for item in evidence_ids):
                rejected.append({"index": index, "reason": "evidence_must_reference_successful_current_run_tool"})
                continue
            try:
                candidate = ProjectMemoryCandidate(
                    project_key=project_key,
                    subject=" ".join(str(raw.get("subject") or "").strip().lower().split()),
                    value=" ".join(str(raw.get("value") or "").strip().split()),
                    evidence_call_ids=list(dict.fromkeys(evidence_ids)),
                    aliases=list(dict.fromkeys(" ".join(str(item).strip().split()) for item in raw.get("aliases") or [] if str(item).strip())),
                )
            except Exception:
                rejected.append({"index": index, "reason": "invalid_candidate"})
                continue
            key = (candidate.project_key, candidate.subject, candidate.value)
            if key in existing:
                rejected.append({"index": index, "reason": "duplicate_candidate"})
                continue
            state.project_memory_candidates.append(candidate)
            existing.add(key)
            accepted += 1
        notes.info("Project memory candidates marked", accepted=accepted, rejected=len(rejected))
        return ToolResult.ok(data={"accepted": accepted, "rejected": rejected}, logs=notes.entries_dict())
