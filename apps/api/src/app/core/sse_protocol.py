from __future__ import annotations
EVENT_META = "meta"
EVENT_TOKEN = "token"
EVENT_DONE = "done"

def sse_error(message: str, *, status: int = 500, title: str | None = None) -> str:
    t = title or "error"
    return f"event: {t}\ndata: {{\"status\":{status},\"error\":{message!r}}}\n\n"
