from __future__ import annotations
from .sse import sse_response as _sse_response
def sse_response(gen):
    return _sse_response(gen)
