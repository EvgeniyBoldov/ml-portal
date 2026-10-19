"""Application-owned flat memory search context."""
from typing import Any, Iterable


def memory_execution_context(scope_keys: Iterable[str], *, revision: int = 0) -> dict[str, Any]:
    return {"type": "execution_context", "revision": revision,
            "scope_keys": list(dict.fromkeys(scope_keys)),
            "search_policy": "parallel_independent_search_per_scope"}
