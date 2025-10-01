from __future__ import annotations
from typing import AsyncIterator, Iterable, Optional, Any
import json
import asyncio
import time

def _line(name: str, value: str) -> str:
    return f"{name}: {value}\n"

def format_sse(data: Any, event: str | None = None, id: str | None = None) -> str:
    """Format a single Server-Sent Event record from a Python object.
    `data` will be JSON-serialized unless it's already a string.
    """
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    parts = []
    if event:
        parts.append(_line("event", event))
    if id:
        parts.append(_line("id", id))
    # multiline-safe: split by newline and prefix "data: "
    for ln in str(data).splitlines() or [""]:
        parts.append(_line("data", ln))
    parts.append("\n")
    return "".join(parts)

async def sse_heartbeat(interval: float = 15.0) -> AsyncIterator[str]:
    """Async generator that yields ping events every `interval` seconds."""
    while True:
        await asyncio.sleep(interval)
        yield format_sse({"ts": int(time.time())}, event="ping")

async def wrap_sse_stream(source: AsyncIterator[str | bytes] | Iterable[str | bytes], *, heartbeat_sec: float = 15.0):
    """Wrap upstream text chunks into SSE `data:` frames and interleave heartbeat pings."""
    async def _aiter(it):
        if hasattr(it, "__aiter__"):
            async for x in it: yield x
        else:
            for x in it: yield x

    ping = sse_heartbeat(heartbeat_sec)
    ping_task = None
    try:
        ping_task = asyncio.create_task(ping.__anext__())
        async for chunk in _aiter(source):
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8", "ignore")
            # push any ready heartbeat first
            if ping_task and ping_task.done():
                try:
                    yield ping_task.result()
                except StopAsyncIteration:
                    pass
                ping_task = asyncio.create_task(ping.__anext__())
            yield format_sse(chunk, event="token")
        # send final heartbeat marker
        if ping_task and ping_task.done():
            try:
                yield ping_task.result()
            except StopAsyncIteration:
                pass
        yield format_sse({"ok": True}, event="done")
    finally:
        if ping_task:
            ping_task.cancel()
