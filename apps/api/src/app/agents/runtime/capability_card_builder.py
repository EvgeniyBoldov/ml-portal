"""Runtime prompt sections for collection-centered and system operations surfaces."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, TYPE_CHECKING

from app.agents.runtime.published_capabilities import (
    build_published_collection_summaries,
    build_published_operation_summary,
)

if TYPE_CHECKING:
    from app.agents.contracts import ResolvedDataInstance, ResolvedOperation


MAX_COLLECTIONS_IN_CARD = 20
MAX_OPERATIONS_IN_CARD = 12


@dataclass(slots=True)
class CapabilityCardBundle:
    collections_card: str = ""
    system_operations_card: str = ""

    @property
    def combined(self) -> str:
        sections = [s for s in (self.collections_card, self.system_operations_card) if s]
        return "\n\n".join(sections)


class CapabilityCardBuilder:
    """Build concise LLM-facing sections for collections and system operations."""

    def build(
        self,
        *,
        resolved_data_instances: Sequence["ResolvedDataInstance"],
        resolved_operations: Sequence["ResolvedOperation"],
        prompt_labels: Optional[dict] = None,
        prompt_budgets: Optional[dict] = None,
    ) -> CapabilityCardBundle:
        labels = prompt_labels if isinstance(prompt_labels, dict) else {}
        budgets = prompt_budgets if isinstance(prompt_budgets, dict) else {}
        return CapabilityCardBundle(
            collections_card=self._build_collections_card(
                resolved_data_instances,
                resolved_operations,
                labels=labels,
                budgets=budgets,
            ),
            system_operations_card=self._build_system_operations_card(
                resolved_operations,
                labels=labels,
                budgets=budgets,
            ),
        )

    def _build_collections_card(
        self,
        items: Sequence["ResolvedDataInstance"],
        operations: Sequence["ResolvedOperation"],
        *,
        labels: Optional[dict] = None,
        budgets: Optional[dict] = None,
    ) -> str:
        if not items:
            return ""
        labels = labels if isinstance(labels, dict) else {}
        budgets = budgets if isinstance(budgets, dict) else {}

        summaries = {
            summary.collection_slug: summary
            for summary in build_published_collection_summaries(items, operations)
        }
        lines: List[str] = [f"## {self._label(labels, 'collections_title', 'Доступные коллекции')}"]
        lines.append(
            f"- {self._label(labels, 'collections_info_rule', 'Перед работой с любой коллекцией сначала вызови `collection.info` для этой коллекции.')}"
        )
        shown = 0
        max_items = self._budget(budgets, "max_collections_in_card", MAX_COLLECTIONS_IN_CARD)
        for item in items:
            slug = self._text(item.collection_slug or item.slug)
            summary = summaries.get(slug)
            if summary is None or not summary.available_operations:
                continue
            if shown >= max_items:
                break
            shown += 1

            collection_type = self._text(summary.collection_type or item.collection_type or item.domain)
            title = self._text(summary.title or getattr(item, "name", None))
            purpose = self._text(summary.purpose)
            data_description = self._text(summary.data_description)
            remote_tables = [self._text(v) for v in (item.remote_tables or []) if self._text(v)]

            lines.append(f"### `{slug}`")
            if title:
                lines.append(f"- {self._label(labels, 'name_label', 'название')}: {title}")
            if collection_type:
                lines.append(f"- {self._label(labels, 'type_label', 'тип')}: {collection_type}")
            if purpose:
                lines.append(f"- {self._label(labels, 'purpose_label', 'назначение')}: {purpose}")
            if data_description:
                lines.append(f"- {self._label(labels, 'data_label', 'данные')}: {data_description}")
            if remote_tables:
                preview = ", ".join(f"`{name}`" for name in remote_tables[:5])
                if len(remote_tables) > 5:
                    preview += f", +{len(remote_tables) - 5} ещё"
                lines.append(f"- {self._label(labels, 'tables_label', 'таблицы')}: {preview}")

        if shown == 0:
            return ""
        total_with_ops = sum(
            1
            for item in items
            if (summary := summaries.get(self._text(item.collection_slug or item.slug)))
            and summary.available_operations
        )
        if total_with_ops > shown:
            lines.append(f"- ... и ещё {total_with_ops - shown} коллекций")
        return "\n".join(lines)

    def _build_system_operations_card(
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

        title = self._label(labels, "system_operations_title", "Системные операции")
        lines: List[str] = [f"## {title}"]
        shown = 0
        max_items = self._budget(budgets, "max_operations_in_card", MAX_OPERATIONS_IN_CARD)
        for op in operations:
            if op.scope != "system":
                continue
            if shown >= max_items:
                break
            shown += 1
            summary = op.published or build_published_operation_summary(op)
            invoke_as = (
                self._text(getattr(op, "operation_slug", None))
                or self._text(getattr(summary, "canonical_name", None))
                or self._text(op.operation)
            )
            display_name = (
                self._text(getattr(summary, "canonical_name", None))
                or self._text(op.operation)
                or invoke_as
            )
            title_text = self._text(getattr(summary, "title", None)) or self._text(op.name)
            details: List[str] = []
            if self._text(getattr(summary, "description", None)):
                details.append(self._text(getattr(summary, "description", None)))
            if self._text(getattr(summary, "result_kind", None)):
                details.append(f"результат: {self._text(getattr(summary, 'result_kind', None))}")
            suffix = f" - {'; '.join(details)}" if details else ""
            lines.append(f"- `{display_name}` ({title_text}){suffix}")

        total = len([item for item in operations if item.scope == "system"])
        if total == 0:
            return ""
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
