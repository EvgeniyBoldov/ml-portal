from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict
from uuid import UUID

import jwt
from redis import Redis

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger(__name__)


def canonical_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def build_operation_fingerprint(*, tool_slug: str, operation: str, args: Dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(str(tool_slug).encode("utf-8"))
    digest.update(b"|")
    digest.update(str(operation).encode("utf-8"))
    digest.update(b"|")
    digest.update(canonical_json(args).encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ConfirmationToken:
    operation_fingerprint: str
    user_id: UUID
    chat_id: UUID
    issued_at: datetime
    nonce: str


class ConfirmationService:
    _fallback_nonce_store: dict[str, float] = {}
    _fallback_nonce_lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self._ttl_seconds = int(getattr(settings, "CONFIRMATION_TTL_SECONDS", 300) or 300)
        confirmation_secret = str(getattr(settings, "CONFIRMATION_SECRET", "") or "").strip()
        if confirmation_secret:
            secret = confirmation_secret
            secret_source = "CONFIRMATION_SECRET"
        else:
            credentials_master_key = str(getattr(settings, "CREDENTIALS_MASTER_KEY", "") or "").strip()
            if credentials_master_key:
                secret = credentials_master_key
                secret_source = "CREDENTIALS_MASTER_KEY"
            else:
                secret = str(
                    getattr(settings, "JWT_SECRET", "change-me-in-production")
                    or "change-me-in-production"
                ).strip()
                secret_source = "JWT_SECRET/default"
            logger.warning(
                "ConfirmationService secret fallback in use (%s); set CONFIRMATION_SECRET explicitly",
                secret_source,
            )
        self._secret = secret
        self._algorithm = "HS256"
        self._nonce_prefix = "runtime:confirmation:nonce:"
        redis_url = str(getattr(settings, "REDIS_URL", "") or "").strip()
        self._redis = Redis.from_url(redis_url, decode_responses=True) if redis_url else None

    def issue(self, *, user_id: UUID, chat_id: UUID, fingerprint: str) -> tuple[str, datetime]:
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        token_data = ConfirmationToken(
            operation_fingerprint=fingerprint,
            user_id=user_id,
            chat_id=chat_id,
            issued_at=issued_at,
            nonce=secrets.token_urlsafe(12),
        )
        payload = {
            "fp": token_data.operation_fingerprint,
            "uid": str(token_data.user_id),
            "cid": str(token_data.chat_id),
            "iat": int(token_data.issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "nonce": token_data.nonce,
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return str(token), expires_at

    def verify(
        self,
        *,
        token: str,
        user_id: UUID,
        chat_id: UUID,
        fingerprint: str,
        consume: bool = False,
    ) -> bool:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except Exception:
            return False
        is_valid = (
            str(payload.get("uid") or "") == str(user_id)
            and str(payload.get("cid") or "") == str(chat_id)
            and str(payload.get("fp") or "") == str(fingerprint)
        )
        if not is_valid:
            return False
        if consume:
            return self._consume_nonce(payload)
        return True

    def _consume_nonce(self, payload: Dict[str, Any]) -> bool:
        nonce = str(payload.get("nonce") or "").strip()
        if not nonce:
            return False
        exp_ts = int(payload.get("exp") or 0)
        ttl = max(1, exp_ts - int(time.time()))
        token_key = f"{self._nonce_prefix}{nonce}"

        if self._redis is not None:
            try:
                created = self._redis.set(token_key, "1", ex=ttl, nx=True)
                if created is not None:
                    return bool(created)
            except Exception as exc:
                logger.warning("Failed to write confirmation nonce to Redis: %s", exc)

        now = time.time()
        expire_at = now + ttl
        with self._fallback_nonce_lock:
            stale = [k for k, ts in self._fallback_nonce_store.items() if ts <= now]
            for key in stale:
                self._fallback_nonce_store.pop(key, None)
            if token_key in self._fallback_nonce_store:
                return False
            self._fallback_nonce_store[token_key] = expire_at
            return True


@lru_cache()
def get_confirmation_service() -> ConfirmationService:
    return ConfirmationService()
