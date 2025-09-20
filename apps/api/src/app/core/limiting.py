from __future__ import annotations
import time
import asyncio
from typing import Optional, Tuple
from fastapi import Request, HTTPException, status

try:
    import aioredis  # type: ignore
except Exception:
    aioredis = None

class RateLimiter:
    def __init__(self, *, redis_url: str | None = None, prefix: str = "rl", limit: int = 60, window_s: int = 60):
        self.redis_url = redis_url
        self.prefix = prefix
        self.limit = limit
        self.window_s = window_s
        self._mem: dict[str, Tuple[int, float]] = {}

    async def allow(self, key: str) -> bool:
        now = time.time()
        if aioredis and self.redis_url:
            r = await aioredis.from_url(self.redis_url)
            win_key = f"{self.prefix}:{int(now // self.window_s)}:{key}"
            val = await r.incr(win_key)
            if val == 1:
                await r.expire(win_key, self.window_s)
            return int(val) <= self.limit
        # Fallback in-memory (per-process)
        win = int(now // self.window_s)
        wk = f"{key}:{win}"
        count, _ = self._mem.get(wk, (0, now))
        count += 1
        self._mem[wk] = (count, now)
        # GC old windows
        for k, (_, ts) in list(self._mem.items()):
            if now - ts > self.window_s * 2:
                self._mem.pop(k, None)
        return count <= self.limit

limiter_default = RateLimiter(limit=60, window_s=60)
