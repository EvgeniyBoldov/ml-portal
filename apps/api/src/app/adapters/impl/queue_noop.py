from typing import Any, Dict, Optional

class NoopQueue:
    """No-op queue adapter used for local/dev.

    Provides the same interface as real queue adapters but does nothing.
    """

    async def publish(self, topic: str, payload: Dict[str, Any], key: Optional[str] = None) -> None:
        return

    async def subscribe(self, topic: str):
        if False:
            yield None  # pragma: no cover
        return
