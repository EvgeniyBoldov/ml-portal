"""Bound protocol corrections between real execution steps."""
from __future__ import annotations

from typing import Any


class ProtocolRepair:
    def __init__(self) -> None:
        self._start: int | None = None

    def apply(self, messages: list[dict[str, Any]], response: str, feedback: str) -> None:
        # Tool results or interaction messages appended since the last repair
        # are execution history and must survive. Replace only our own tail.
        if self._start is not None and len(messages) == self._start + 2:
            del messages[self._start:]
        self._start = len(messages)
        messages.extend([{"role": "assistant", "content": response}, {"role": "user", "content": feedback}])
