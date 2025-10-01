"""
app/utils/sse.py
Common SSE response with heartbeats and correct headers.
"""
from __future__ import annotations
from typing import AsyncIterator
from starlette.responses import StreamingResponse
import time, asyncio

HEARTBEAT = b":keep-alive\n\n"

async def _hb(gen: AsyncIterator[bytes], interval: float = 15.0):
    last = time.monotonic()
    async for chunk in gen:
        yield chunk
        now = time.monotonic()
        if now - last >= interval:
            yield HEARTBEAT
            last = now

def sse_response(generator: AsyncIterator[bytes], heartbeat_interval: float = 15.0) -> StreamingResponse:
    return StreamingResponse(
        _hb(generator, heartbeat_interval),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-store","Connection":"keep-alive","X-Accel-Buffering":"no"},
    )
