# Cursor TODO: migrate to `get_settings()` and finish backend polish

## 1) Replace all usages of module-level `settings` with `get_settings()`
We want **zero** imports like `from app.core.config import settings`. Everywhere, import the getter once per module/function and use a local variable.

### Find/Replace rules
Search patterns (regex):
- `from\s+app\.core\.config\s+import\s+settings\b`
- `\bsettings\.`  (after removing the import, convert these to `s.`)

Replacement strategy (example):
```python
# BEFORE
from app.core.config import settings
timeout = settings.HTTP_TIMEOUT_SECONDS

# AFTER
from app.core.config import get_settings
s = get_settings()
timeout = s.HTTP_TIMEOUT_SECONDS
```

Special cases:
- Functions or async tasks: prefer calling `s = get_settings()` **inside** the function if the value can change per process/env (rare). Otherwise, module-level `s = get_settings()` is OK.
- Do not keep any `settings = get_settings()` aliases — we use only `get_settings()`.


## 2) Update DI and factories
- In `app/core/di.py` (and similar), ensure all constructors read from `s = get_settings()` for timeouts, retry counts, base URLs, and circuit breaker thresholds.
- Verify that `cleanup_clients()` still closes all instantiated clients.

## 3) SSE contract and errors
- Use `app.core.sse_protocol` constants in all stream endpoints (`chat`, `analyze`, etc.).
  - Allowed events: `EVENT_META`, `EVENT_TOKEN`, `EVENT_DONE`, `EVENT_ERROR`, `EVENT_PING`.
  - For errors in a stream, emit a single SSE frame with `event: error` and a JSON payload:
    ```json
    {"type":"about:blank","title":"LLM upstream error","status":502,"detail":"<message>"}
    ```
- Non-stream endpoints must return ProblemDetails JSON via `HTTPException` or handlers.

## 4) ProblemDetails consistency
- Ensure all routers return ProblemDetails on 4xx/5xx.
- Map domain exceptions (e.g., circuit breaker open) to 503/502 as appropriate.

## 5) Remove legacy/duplicate adapters
After Stage 1:
- Remove: `apps/api/src/app/adapters/impl/llm_http.py`, `emb_http.py`, `s3_minio.py`, `adapters/utils/http.py` if still present.

## 6) Env/Settings parity
- Confirm that every env var referenced by code exists in `Settings` (`core/config.py`) and vice versa.
- Make sure `.env`/`.env.test` include required keys (DB, Redis, JWT, S3, Qdrant, HTTP, Idempotency, Celery).

## 7) Lint gates for CI
- Add a CI check (or pre-commit) that fails if `from app.core.config import settings` appears anywhere.
  - Example grep: `grep -R "from app.core.config import settings" apps/api/src/app | wc -l` must equal 0.
- Optional: mypy rule to disallow shadowed `settings` name.

## 8) Quick smoke after migration
- Start API, call `/metrics`, `/api/v1/chat` (mock upstream), `/api/v1/chat/stream`, `/api/v1/analyze/stream`, and any RAG presign route.
- Verify `X-Request-ID` and `X-RateLimit-*` headers presence where applicable.
