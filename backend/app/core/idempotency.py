from __future__ import annotations
import os, json, base64, hashlib
from typing import List, Tuple, Optional, Dict, Any
from starlette.types import ASGIApp, Scope, Receive, Send, Message
from app.core.redis import get_redis

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
DEFAULT_TTL = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"))
ENABLED = os.getenv("IDEMPOTENCY_ENABLED", "1") not in {"0", "false", "False"}
MAX_CAPTURE_BYTES = int(os.getenv("IDEMPOTENCY_MAX_BYTES", "1048576"))  # 1 MiB

def _get_header(headers: List[Tuple[bytes, bytes]], name: str) -> Optional[bytes]:
    name_b = name.lower().encode()
    for k, v in headers:
        if k.lower() == name_b:
            return v
    return None

class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if not ENABLED or scope.get("type") != "http":
            return await self.app(scope, receive, send)

        method = scope.get("method") or "GET"
        if method in SAFE_METHODS:
            return await self.app(scope, receive, send)

        headers: List[Tuple[bytes, bytes]] = scope.get("headers") or []
        idem_key_b = _get_header(headers, "idempotency-key")
        if not idem_key_b:
            return await self.app(scope, receive, send)

        path = scope.get("path") or "/"
        auth_b = _get_header(headers, "authorization") or b""
        user_hash = hashlib.sha256(auth_b).hexdigest()[:16] if auth_b else "anon"
        raw_key = b"|".join([method.encode(), path.encode(), idem_key_b, user_hash.encode()])
        key_hash = hashlib.sha256(raw_key).hexdigest()
        rkey = f"idemp:v1:{key_hash}"

        redis = get_redis()
        try:
            cached = await redis.get(rkey)  # type: ignore[attr-defined]
        except Exception:
            cached = None

        if cached:
            try:
                data = json.loads(cached)
                body = base64.b64decode(data.get("body_b64", ""))
                from starlette.responses import Response
                headers_dict = data.get("headers") or {}
                headers_dict["content-length"] = str(len(body))
                resp = Response(content=body, status_code=int(data.get("status", 200)), headers=headers_dict, media_type=None)
                return await resp(scope, receive, send)
            except Exception:
                pass

        started: Dict[str, Any] = {"status": None, "headers": []}
        chunks: list[bytes] = []
        total = 0
        is_streaming = False

        async def send_wrapper(message: Message):
            nonlocal total, is_streaming
            if message["type"] == "http.response.start":
                started["status"] = message["status"]
                started["headers"] = message.get("headers", [])
                ctype = _get_header(started["headers"], "content-type") or b""
                if b"text/event-stream" in ctype or b"stream" in ctype:
                    is_streaming = True
                return await send(message)
            elif message["type"] == "http.response.body":
                body = message.get("body", b"") or b""
                if body:
                    total += len(body)
                    if total <= MAX_CAPTURE_BYTES:
                        chunks.append(body)
                    else:
                        is_streaming = True
                return await send(message)
            else:
                return await send(message)

        await self.app(scope, receive, send_wrapper)

        if not is_streaming and started["status"] is not None:
            try:
                body_bytes = b"".join(chunks)
                headers_dict = {k.decode().lower(): v.decode() for k, v in (started["headers"] or [])}
                payload = {
                    "status": int(started["status"]),
                    "headers": headers_dict,
                    "body_b64": base64.b64encode(body_bytes).decode(),
                }
                await redis.setex(rkey, DEFAULT_TTL, json.dumps(payload))  # type: ignore[attr-defined]
            except Exception:
                pass
