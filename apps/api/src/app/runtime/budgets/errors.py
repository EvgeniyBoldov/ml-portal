from __future__ import annotations


class BudgetExceededError(RuntimeError):
    def __init__(self, *, scope: str, metric: str, used: int, limit: int) -> None:
        super().__init__(f"Budget exceeded ({scope}.{metric}): used={used} limit={limit}")
        self.scope = scope
        self.metric = metric
        self.used = used
        self.limit = limit
