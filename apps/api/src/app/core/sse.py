from __future__ import annotations
import json
from typing import Any, AsyncIterator, Callable
from fastapi.responses import StreamingResponse
from .sse_protocol import EVENT_DONE

def format_sse(data: Any, event: str | None = None) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {payload}\n\n"

async def wrap_sse_stream(ait: AsyncIterator[str]):
    async for chunk in ait:
        yield chunk
    yield format_sse({"ok": True}, event=EVENT_DONE)

def sse_response(gen: Callable[[], AsyncIterator[str]]) -> StreamingResponse:
    return StreamingResponse(gen(), media_type="text/event-stream")
