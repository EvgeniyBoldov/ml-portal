Ensure your `wrap_sse_stream` sends periodic heartbeats (e.g., every 15s) and sets:
- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no` (via Nginx conf)
- `Connection: keep-alive`

Idempotency guard explicitly skips caching for stream endpoints.
