"""Runtime capability card builder for planner/executor prompts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.contracts import ResolvedDataInstance, ResolvedOperation
    from app.agents.execution_preflight import ExecutionRequest


MAX_COLLECTIONS_IN_CARD = 20
MAX_OPERATIONS_IN_CARD = 12


@dataclass(slots=True)
class CapabilityCardBundle:
    agent_card: str = ""
    collections_card: str = ""
    operations_card: str = ""

    @property
    def combined(self) -> str:
        sections = [s for s in (self.agent_card, self.collections_card, self.operations_card) if s]
        if not sections:
            return ""
        return "## Runtime Capability Card\n\n" + "\n\n".join(sections)


class CapabilityCardBuilder:
    """Build concise, structured runtime cards for agent + collections + operations."""

    def build(
        self,
        *,
        exec_request: "ExecutionRequest",
        resolved_operations: Sequence["ResolvedOperation"],
    ) -> CapabilityCardBundle:
        return CapabilityCardBundle(
            agent_card=self._build_agent_card(exec_request),
            collections_card=self._build_collections_card(exec_request.resolved_data_instances),
            operations_card=self._build_operations_card(resolved_operations),
        )

    def _build_agent_card(self, exec_request: "ExecutionRequest") -> str:
        agent = exec_request.agent
        if agent is None:
            return ""

        lines: List[str] = ["### Agent", f"- Slug: `{self._text(getattr(agent, 'slug', ''))}`"]

        title = self._text(getattr(agent, "name", ""))
        if title:
            lines.append(f"- Title: {title}")

        description = self._text(getattr(agent, "description", ""))
        if description:
            lines.append(f"- Description: {description}")

        tags = [self._text(tag) for tag in (getattr(agent, "tags", None) or [])]
        tags = [tag for tag in tags if tag]
        if tags:
            lines.append(f"- Tags: {', '.join(tags)}")

        agent_version = exec_request.agent_version
        if agent_version is not None:
            risk_level = self._text(getattr(agent_version, "risk_level", ""))
            if risk_level:
                lines.append(f"- Risk level: {risk_level}")

        return "\n".join(lines)

    def _build_collections_card(self, items: Sequence["ResolvedDataInstance"]) -> str:
        if not items:
            return ""

        lines: List[str] = ["### Collections"]
        shown = 0
        for item in items:
            if shown >= MAX_COLLECTIONS_IN_CARD:
                break
            shown += 1
            slug = self._text(item.collection_slug or item.slug)
            collection_type = self._text(item.collection_type or item.domain)
            entity_type = self._text(item.entity_type)
            purpose = self._text(item.usage_purpose)
            data_description = self._text(item.data_description)
            description = self._text(item.description)
            remote_tables = [self._text(v) for v in (item.remote_tables or []) if self._text(v)]
            readiness = getattr(item, "readiness", None)

            line = f"- `{slug}`"
            details: List[str] = []
            if collection_type:
                details.append(f"type: {collection_type}")
            if readiness is not None:
                readiness_status = self._text(getattr(readiness, "status", ""))
                if readiness_status:
                    details.append(f"readiness: {readiness_status}")
                schema_freshness = self._text(getattr(readiness, "schema_freshness", ""))
                if schema_freshness:
                    details.append(f"schema: {schema_freshness}")
            if entity_type:
                details.append(f"entity: {entity_type}")
            if purpose:
                details.append(f"purpose: {purpose}")
            if data_description:
                details.append(f"data: {data_description}")
            elif description:
                details.append(f"about: {description}")
            if remote_tables:
                preview = ", ".join(f"`{name}`" for name in remote_tables[:5])
                if len(remote_tables) > 5:
                    preview += f", +{len(remote_tables) - 5} more"
                details.append(f"tables: {preview}")
            if readiness is not None:
                missing = list(getattr(readiness, "missing_requirements", []) or [])
                if missing:
                    details.append(f"missing: {', '.join(self._text(v) for v in missing if self._text(v))}")
            if details:
                line += " - " + "; ".join(details)
            lines.append(line)

        total = len(items)
        if total > shown:
            lines.append(f"- ... and {total - shown} more collections")
        return "\n".join(lines)

    def _build_operations_card(self, operations: Sequence["ResolvedOperation"]) -> str:
        if not operations:
            return ""

        lines: List[str] = [f"### Allowed Operations ({len(operations)})"]
        shown = 0
        for op in operations:
            if shown >= MAX_OPERATIONS_IN_CARD:
                break
            shown += 1
            data_slug = self._text(op.data_instance_slug)
            line = f"- `{op.operation_slug}`"
            details: List[str] = []
            if data_slug:
                details.append(f"collection: {data_slug}")
            if details:
                line += " - " + "; ".join(details)
            lines.append(line)

        total = len(operations)
        if total > shown:
            lines.append(f"- ... and {total - shown} more operations")
        return "\n".join(lines)

    @staticmethod
    def _text(value: Optional[Any]) -> str:
        return str(value or "").strip()
