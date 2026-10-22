"""Wall-time deadlines for runtime phases and their LLM-backed streams."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


def _timeout_seconds(wall_time_ms: int | None) -> float | None:
    if wall_time_ms is None:
        return None
    return max(0, wall_time_ms) / 1000


def _remaining_wall_time_ms(started_at: float, wall_time_ms: int | None) -> int | None:
    if wall_time_ms is None:
        return None
    elapsed_ms = int((asyncio.get_running_loop().time() - started_at) * 1000)
    return max(0, wall_time_ms - elapsed_ms)


async def iter_with_phase_deadline(
    events: AsyncIterator[Any],
    wall_time_ms: int | None,
) -> AsyncIterator[Any]:
    """Consume an async event stream under one elapsed-time deadline."""
    async with asyncio.timeout(_timeout_seconds(wall_time_ms)):
        async for event in events:
            yield event


async def stream_synthesis_with_deadline(
    synthesizer: Any,
    *,
    budget_registry: Any,
    budget_resolver: Any,
    sandbox_overrides: dict[str, Any] | None,
    **stream_kwargs: Any,
) -> AsyncIterator[Any]:
    """Pass budget controls to Synthesizer and enforce its configured phase deadline."""
    started_at = asyncio.get_running_loop().time()
    limits = None
    if budget_resolver is not None:
        try:
            limits = await budget_resolver.resolve_orchestrator("synthesizer", sandbox_overrides)
        except Exception:
            # Synthesizer.stream retains its existing safe fallback when limits
            # cannot be resolved. The deadline is unavailable in that case.
            limits = None
    events = synthesizer.stream(
        **stream_kwargs,
        sandbox_overrides=sandbox_overrides,
        budget_registry=budget_registry,
        budget_resolver=budget_resolver,
    )
    remaining_ms = _remaining_wall_time_ms(started_at, getattr(limits, "wall_time_ms", None))
    async for event in iter_with_phase_deadline(events, remaining_ms):
        yield event
