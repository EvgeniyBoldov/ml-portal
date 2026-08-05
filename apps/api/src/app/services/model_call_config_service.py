"""Resolve typed call policy from the selected LLM model deployment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_registry import Model


@dataclass(frozen=True)
class ModelCallConfig:
    max_output_tokens: Optional[int]
    request_timeout_s: int
    max_retries: int


class ModelCallConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, alias_or_provider_name: Optional[str]) -> ModelCallConfig:
        if not alias_or_provider_name:
            return ModelCallConfig(max_output_tokens=None, request_timeout_s=30, max_retries=2)
        row = (await self.session.execute(
            select(Model).where(
                (Model.alias == alias_or_provider_name) | (Model.provider_model_name == alias_or_provider_name),
                Model.deleted_at.is_(None),
            ).limit(1)
        )).scalar_one_or_none()
        if row is None:
            return ModelCallConfig(max_output_tokens=None, request_timeout_s=30, max_retries=2)
        legacy = dict(row.extra_config or {})
        return ModelCallConfig(
            max_output_tokens=int(row.max_output_tokens or legacy.get("max_tokens")) if (row.max_output_tokens or legacy.get("max_tokens")) else None,
            request_timeout_s=max(1, int(row.request_timeout_s or 30)),
            max_retries=max(0, int(row.max_retries if row.max_retries is not None else 2)),
        )
