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
        return "## Карточка возможностей\n\n" + "\n\n".join(sections)


class CapabilityCardBuilder:
    """Build concise, structured runtime cards for agent + collections + operations."""

    def build(
        self,
        *,
        exec_request: "ExecutionRequest",
        resolved_operations: Sequence["ResolvedOperation"],
        prompt_labels: Optional[dict] = None,
        prompt_budgets: Optional[dict] = None,
    ) -> CapabilityCardBundle:
        labels = prompt_labels if isinstance(prompt_labels, dict) else {}
        budgets = prompt_budgets if isinstance(prompt_budgets, dict) else {}
        return CapabilityCardBundle(
            agent_card=self._build_agent_card(exec_request, labels=labels),
            collections_card=self._build_collections_card(
                exec_request.resolved_data_instances,
                labels=labels,
                budgets=budgets,
            ),
            operations_card=self._build_operations_card(resolved_operations, labels=labels, budgets=budgets),
        )

    def _build_agent_card(self, exec_request: "ExecutionRequest", *, labels: Optional[dict] = None) -> str:
        agent = exec_request.agent
        if agent is None:
            return ""
        labels = labels if isinstance(labels, dict) else {}

        lines: List[str] = [f"### {self._label(labels, 'agent_title', 'Агент')}", f"- {self._label(labels, 'slug_label', 'Slug')}: `{self._text(getattr(agent, 'slug', ''))}`"]

        title = self._text(getattr(agent, "name", ""))
        if title:
            lines.append(f"- {self._label(labels, 'name_label', 'Название')}: {title}")

        description = self._text(getattr(agent, "description", ""))
        if description:
            lines.append(f"- {self._label(labels, 'description_label', 'Описание')}: {description}")

        tags = [self._text(tag) for tag in (getattr(agent, "tags", None) or [])]
        tags = [tag for tag in tags if tag]
        if tags:
            lines.append(f"- {self._label(labels, 'tags_label', 'Теги')}: {', '.join(tags)}")

        agent_version = exec_request.agent_version
        if agent_version is not None:
            risk_level = self._text(getattr(agent_version, "risk_level", ""))
            if risk_level:
                lines.append(f"- {self._label(labels, 'risk_label', 'Уровень риска')}: {risk_level}")

        return "\n".join(lines)

    def _build_collections_card(
        self,
        items: Sequence["ResolvedDataInstance"],
        *,
        labels: Optional[dict] = None,
        budgets: Optional[dict] = None,
    ) -> str:
        if not items:
            return ""
        labels = labels if isinstance(labels, dict) else {}
        budgets = budgets if isinstance(budgets, dict) else {}

        lines: List[str] = [f"### {self._label(labels, 'collections_title', 'Коллекции')}"]
        shown = 0
        max_items = self._budget(budgets, "max_collections_in_card", MAX_COLLECTIONS_IN_CARD)
        for item in items:
            if shown >= max_items:
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
                details.append(f"{self._label(labels, 'type_label', 'тип')}: {collection_type}")
            if readiness is not None:
                readiness_status = self._text(getattr(readiness, "status", ""))
                if readiness_status:
                    details.append(f"{self._label(labels, 'status_label', 'готовность')}: {readiness_status}")
                schema_freshness = self._text(getattr(readiness, "schema_freshness", ""))
                if schema_freshness:
                    details.append(f"{self._label(labels, 'schema_label', 'схема')}: {schema_freshness}")
            if entity_type:
                details.append(f"{self._label(labels, 'entity_type_label', 'сущность')}: {entity_type}")
            if purpose:
                details.append(f"{self._label(labels, 'purpose_label', 'назначение')}: {purpose}")
            if data_description:
                details.append(f"{self._label(labels, 'data_label', 'данные')}: {data_description}")
            elif description:
                details.append(f"{self._label(labels, 'description_label', 'описание')}: {description}")
            if remote_tables:
                preview = ", ".join(f"`{name}`" for name in remote_tables[:5])
                if len(remote_tables) > 5:
                    preview += f", +{len(remote_tables) - 5} ещё"
                details.append(f"{self._label(labels, 'tables_label', 'таблицы')}: {preview}")
            if readiness is not None:
                missing = list(getattr(readiness, "missing_requirements", []) or [])
                if missing:
                    details.append(f"{self._label(labels, 'missing_label', 'отсутствует')}: {', '.join(self._text(v) for v in missing if self._text(v))}")
            if details:
                line += " - " + "; ".join(details)
            lines.append(line)

        total = len(items)
        if total > shown:
            lines.append(f"- ... и ещё {total - shown} коллекций")
        return "\n".join(lines)

    def _build_operations_card(
        self,
        operations: Sequence["ResolvedOperation"],
        *,
        labels: Optional[dict] = None,
        budgets: Optional[dict] = None,
    ) -> str:
        if not operations:
            return ""
        labels = labels if isinstance(labels, dict) else {}
        budgets = budgets if isinstance(budgets, dict) else {}

        title = self._label(labels, 'operations_title', 'Доступные операции')
        lines: List[str] = [f"### {title} ({len(operations)})"]
        shown = 0
        max_items = self._budget(budgets, "max_operations_in_card", MAX_OPERATIONS_IN_CARD)
        for op in operations:
            if shown >= max_items:
                break
            shown += 1
            coll_slug = self._text(getattr(op, "collection_slug", None) or op.data_instance_slug)
            line = f"- `{op.operation_slug}`"
            details: List[str] = []
            if coll_slug:
                details.append(f"{self._label(labels, 'collection_label', 'коллекция')}: {coll_slug}")
            if details:
                line += " - " + "; ".join(details)
            lines.append(line)

        total = len(operations)
        if total > shown:
            lines.append(f"- ... и ещё {total - shown} операций")
        return "\n".join(lines)

    @staticmethod
    def _label(labels: dict, key: str, default: str) -> str:
        value = labels.get(key)
        return str(value).strip() if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _budget(budgets: dict, key: str, default: int) -> int:
        def _coerce(value: Any) -> Optional[int]:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return None
            return parsed if parsed > 0 else None

        direct = _coerce(budgets.get(key))
        if direct is not None:
            return direct
        for section in ("capability_card", "prompt_assembler", "operations"):
            section_value = budgets.get(section)
            if isinstance(section_value, dict):
                nested = _coerce(section_value.get(key))
                if nested is not None:
                    return nested
        return default

    @staticmethod
    def _text(value: Optional[Any]) -> str:
        return str(value or "").strip()
