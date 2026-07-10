"""TemplateDescriptionBuilder — semantic description from template contract."""
from __future__ import annotations
import json, logging
from typing import Any, Optional
from app.services.collection.template_contract import (
    TemplateContract,
)

logger = logging.getLogger(__name__)

DESCRIPTION_SYSTEM_PROMPT = """You generate clear, concise template descriptions in Russian.
Summarize: purpose, target audience, key fields (scalars and tables), and usage notes.
Keep under 200 words."""


class TemplateDescriptionBuilder:
    """Build semantic description from contract using LLM or deterministic summary."""

    def __init__(self, llm: Optional[Any] = None):
        self.llm = llm

    async def build(
        self,
        contract: TemplateContract,
        title: Optional[str] = None,
        version: Optional[str] = None,
    ) -> str:
        """Generate description from contract."""
        desc = await self._llm_build(contract, title, version)
        if desc is None:
            desc = self._deterministic_build(contract, title, version)
        return desc

    async def _llm_build(
        self,
        contract: TemplateContract,
        title: Optional[str],
        version: Optional[str],
    ) -> Optional[str]:
        if self.llm is None:
            return None
        try:
            prompt = self._build_prompt(contract, title, version)
            resp = await self.llm.chat(
                [
                    {"role": "system", "content": DESCRIPTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                params={"temperature": 0.3, "max_tokens": 500},
            )
            return resp.get("content", "").strip()
        except Exception as e:
            logger.warning(f"LLM description failed: {e}")
            return None

    def _build_prompt(
        self,
        contract: TemplateContract,
        title: Optional[str],
        version: Optional[str],
    ) -> str:
        runtime_schema = contract.to_prompt_schema()
        lines = [f"Title: {title or 'N/A'}"]
        if version:
            lines.append(f"Version: {version}")
        lines.append(f"Format: {contract.format.value if contract.format else 'unknown'}")
        lines.append("")
        lines.append("Runtime schema:")
        lines.append(json.dumps(runtime_schema, ensure_ascii=False, indent=2))
        return "\n".join(lines)

    def _deterministic_build(
        self,
        contract: TemplateContract,
        title: Optional[str],
        version: Optional[str],
    ) -> str:
        """Fallback: deterministic summary without LLM."""
        lines = []
        t = title or "Шаблон документа"
        lines.append(f"{t}")
        if version:
            lines.append(f"Версия: {version}")
        lines.append("")
        scalars = contract.scalar_fields()
        tables = contract.table_fields()
        if scalars:
            lines.append("Поля:")
            for f in scalars:
                req = "обязательное" if f.required else "необязательное"
                lines.append(f"  • {f.label} — {req}")
        if tables:
            lines.append("Таблицы:")
            for t_field in tables:
                req = "обязательная" if t_field.required else "необязательная"
                cols = ", ".join(c.label for c in t_field.columns)
                lines.append(f"  • {t_field.label} ({req}) — колонки: {cols}")
        return "\n".join(lines)
