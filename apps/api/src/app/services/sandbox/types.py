from __future__ import annotations

from typing import Any, Dict

from app.models.sandbox import SandboxOverrideSnapshot, SandboxRun


class SandboxRunPreparation:
    """Resolved sandbox run inputs produced from a session branch snapshot."""

    __slots__ = ("snapshot", "effective_config", "run")

    def __init__(
        self,
        *,
        snapshot: SandboxOverrideSnapshot,
        effective_config: Dict[str, Any],
        run: SandboxRun,
    ) -> None:
        self.snapshot = snapshot
        self.effective_config = effective_config
        self.run = run

