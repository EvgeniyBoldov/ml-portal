from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

import jwt

from app.core.config import get_settings


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
    def __init__(self) -> None:
        settings = get_settings()
        self._ttl_seconds = int(getattr(settings, "CONFIRMATION_TTL_SECONDS", 300) or 300)
        secret = (
            str(getattr(settings, "CONFIRMATION_SECRET", "") or "").strip()
            or str(getattr(settings, "CREDENTIALS_MASTER_KEY", "") or "").strip()
            or str(getattr(settings, "JWT_SECRET", "change-me-in-production") or "change-me-in-production").strip()
        )
        self._secret = secret
        self._algorithm = "HS256"

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
    ) -> bool:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except Exception:
            return False
        return (
            str(payload.get("uid") or "") == str(user_id)
            and str(payload.get("cid") or "") == str(chat_id)
            and str(payload.get("fp") or "") == str(fingerprint)
        )
