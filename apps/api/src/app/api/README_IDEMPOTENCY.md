# Idempotency Guard

Add to mutation handlers (POST/PUT) like:

```python
from fastapi import Depends
from app.api.deps_idempotency import idempotency_guard

@router.post("/messages", dependencies=[Depends(lambda request: idempotency_guard(request, scope="chat:message"))])
async def post_message(...):
    ...
```

- Uses Redis `SET key value NX EX ttl` to ensure (scope, key) uniqueness.
- Absence of `Idempotency-Key` header **does not** block the call (explicit design).
- On duplicate within TTL returns `409 Conflict` with `Retry-After` header.
