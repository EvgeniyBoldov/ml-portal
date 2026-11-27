"""Generate high entropy bearer tokens and verify their stored hashes."""
import hashlib
import hmac
import secrets
from uuid import UUID, uuid4


def issue_token(prefix: str) -> tuple[UUID, str, str]:
    token_id = uuid4()
    raw = f"{prefix}{token_id.hex}.{secrets.token_urlsafe(32)}"
    return token_id, raw, hashlib.sha256(raw.encode()).hexdigest()


def token_matches(raw: str, digest: str) -> bool:
    return hmac.compare_digest(digest, hashlib.sha256(raw.encode()).hexdigest())
