"""Keep final routing decisions grounded in the scope actually recalled."""
from typing import Any, Awaitable, Callable

from app.runtime.memory.effective_scope import EffectiveScopeContext
from app.runtime.turn_preflight import TurnPreflightDecision


async def recall_with_stable_scope(
    scope: EffectiveScopeContext,
    *,
    search: Callable[[EffectiveScopeContext], Awaitable[dict[str, Any]]],
    complete: Callable[[dict[str, Any], EffectiveScopeContext], Awaitable[TurnPreflightDecision]],
    select: Callable[[EffectiveScopeContext, TurnPreflightDecision], Awaitable[EffectiveScopeContext]],
) -> tuple[dict[str, Any], TurnPreflightDecision, EffectiveScopeContext]:
    for _ in range(3):
        recalled = await search(scope)
        if recalled.get("success") is False:
            raise ValueError(str(recalled.get("error_code") or "invalid_memory_scope"))
        actual = set((recalled.get("search_scope") or {}).get("scope_keys") or [])
        if actual != set(scope.keys):
            raise ValueError("recall_scope_mismatch")
        decision = await complete(recalled, scope)
        selected = await select(scope, decision)
        if set(selected.keys) == set(scope.keys) or decision.route == "clarify":
            return recalled, decision, selected
        scope = selected
    raise ValueError("recall_scope_unstable")
