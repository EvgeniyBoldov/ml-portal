from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _channel(stream_key: str) -> str:
    return f"runtime:tail:{stream_key}"


def _control_channel(run_id: str) -> str:
    return f"runtime:control:{run_id}"


class RuntimeTailEventBus:
    """Redis pub/sub bridge for async runtime tail events."""

    def __init__(self, redis_client: Optional[Any] = None) -> None:
        self._redis = redis_client

    def _redis_client(self):
        if self._redis is not None:
            return self._redis
        settings = get_settings()
        return aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    async def publish(self, *, stream_key: str, payload: dict[str, Any]) -> None:
        redis_client = self._redis_client()
        data = dict(payload)
        data.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        await redis_client.publish(_channel(stream_key), json.dumps(data, ensure_ascii=False, default=str))
        if self._redis is None:
            await redis_client.aclose()


class RuntimeTailSubscriber:
    """Subscriber for runtime tail events of a single stream key."""

    def __init__(self, *, stream_key: str, redis_client: Optional[Any] = None) -> None:
        self._stream_key = stream_key
        self._redis = redis_client
        self._owned_client = None
        self._pubsub = None

    async def subscribe(self) -> None:
        redis_client = self._redis
        if redis_client is None:
            settings = get_settings()
            redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            self._owned_client = redis_client
        self._pubsub = redis_client.pubsub()
        await self._pubsub.subscribe(_channel(self._stream_key))

    async def listen(self) -> AsyncGenerator[dict[str, Any], None]:
        if self._pubsub is None:
            await self.subscribe()
        assert self._pubsub is not None
        async for message in self._pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                raw = message.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if not isinstance(raw, str) or not raw:
                    continue
                decoded = json.loads(raw)
                if isinstance(decoded, dict):
                    yield decoded
            except Exception as exc:  # noqa: BLE001
                logger.warning("RuntimeTailSubscriber decode failed: %s", exc)

    async def unsubscribe(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.unsubscribe(_channel(self._stream_key))
            await self._pubsub.close()
            self._pubsub = None
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None


class RuntimeRunControlBus:
    """Best-effort cross-process control signals for a live runtime run."""

    async def publish_cancel(self, run_id: str) -> None:
        settings = get_settings()
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await redis_client.publish(_control_channel(run_id), "cancel")
        finally:
            await redis_client.aclose()


class RuntimeRunControlSubscriber:
    """Wait for a cancellation signal without coupling execution to an SSE client."""

    def __init__(self, *, run_id: str) -> None:
        self._run_id = run_id
        self._redis = None
        self._pubsub = None

    async def subscribe(self) -> None:
        settings = get_settings()
        self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(_control_channel(self._run_id))

    async def wait_for_cancel(self) -> None:
        if self._pubsub is None:
            await self.subscribe()
        assert self._pubsub is not None
        async for message in self._pubsub.listen():
            if message.get("type") != "message":
                continue
            if str(message.get("data") or "") == "cancel":
                return

    async def unsubscribe(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.unsubscribe(_control_channel(self._run_id))
            await self._pubsub.close()
            self._pubsub = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
