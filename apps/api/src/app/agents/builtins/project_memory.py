"""System tools for reading and proposing project memory."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.runtime.project_memory_candidates import ProjectMemoryCandidate
from app.services.project_memory_service import ProjectMemoryService

_READ_INPUT = {
    "type": "object",
    "properties": {
        "project_key": {"type": "string", "minLength": 1},
        "subject_prefix": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": ["project_key"],
    "additionalProperties": False,
}
_READ_OUTPUT = {
    "type": "object",
    "properties": {"project": {"type": ["object", "null"]}, "facts": {"type": "array"}, "count": {"type": "integer"}},
    "required": ["project", "facts", "count"],
}
_MARK_INPUT = {
    "type": "object",
    "properties": {
        "project_key": {"type": "string", "minLength": 1},
        "candidates": {
            "type": "array", "minItems": 1, "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "minLength": 1},
                    "value": {"type": "string", "minLength": 1},
                    "evidence_call_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["subject", "value", "evidence_call_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["project_key", "candidates"],
    "additionalProperties": False,
}
_MARK_OUTPUT = {
    "type": "object",
    "properties": {"accepted": {"type": "integer"}, "rejected": {"type": "array"}},
    "required": ["accepted", "rejected"],
}


@register_tool
class ProjectMemoryReadTool(VersionedTool):
    tool_slug: ClassVar[str] = "project_memory.read"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Read Project Memory"
    description: ClassVar[str] = "Read confirmed compact knowledge for an exact project key."

    @tool_version(version="1.0.0", input_schema=_READ_INPUT, output_schema=_READ_OUTPUT, description="Read confirmed project memory")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes(self.tool_slug)
        project_key = str(args.get("project_key") or "").strip().lower()
        if not project_key:
            return ToolResult.fail("Missing 'project_key' argument", logs=log.entries_dict())
        session_factory = ctx.get_runtime_deps().session_factory
        if session_factory is None:
            from app.core.db import get_session_factory
            session_factory = get_session_factory()
        async with session_factory() as session:
            data = await ProjectMemoryService(session).read(
                project_key=project_key,
                subject_prefix=str(args.get("subject_prefix") or "").strip() or None,
                limit=int(args.get("limit") or 20),
            )
        log.info("Project memory read", project_key=project_key, count=data["count"])
        return ToolResult.ok(data=data, logs=log.entries_dict())


@register_tool
class ProjectMemoryMarkTool(VersionedTool):
    tool_slug: ClassVar[str] = "project_memory.mark"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Mark Project Memory Candidates"
    description: ClassVar[str] = "Mark evidenced project knowledge for asynchronous review; this never writes durable memory."

    @tool_version(version="1.0.0", input_schema=_MARK_INPUT, output_schema=_MARK_OUTPUT, description="Mark evidenced project memory candidates in current run state")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes(self.tool_slug)
        state = ctx.extra.get("runtime_turn_state")
        ledger = ctx.extra.get("runtime_tool_ledger")
        if state is None or not hasattr(state, "project_memory_candidates") or ledger is None:
            return ToolResult.fail("Project memory marking is available only during a runtime turn.", logs=log.entries_dict())
        project_key = str(args.get("project_key") or "").strip().lower()
        if not project_key:
            return ToolResult.fail("Missing 'project_key' argument", logs=log.entries_dict())
        valid_ids = {
            entry.call_id
            for entry in ledger.entries
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
        log.info("Project memory candidates marked", accepted=accepted, rejected=len(rejected))
        return ToolResult.ok(data={"accepted": accepted, "rejected": rejected}, logs=log.entries_dict())
