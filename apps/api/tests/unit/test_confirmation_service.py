from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import jwt

from app.agents.runtime.confirmation import ConfirmationService


def test_issue_and_verify_happy_path():
    service = ConfirmationService()
    user_id = uuid4()
    chat_id = uuid4()
    fingerprint = "abc123fingerprint"

    token, expires_at = service.issue(
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
    )

    assert token
    assert isinstance(expires_at, datetime)
    assert expires_at.tzinfo == timezone.utc
    assert service.verify(
        token=token,
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
    )


def test_verify_rejects_other_user_or_fingerprint():
    service = ConfirmationService()
    user_id = uuid4()
    chat_id = uuid4()
    fingerprint = "abc123fingerprint"
    token, _ = service.issue(
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
    )

    assert not service.verify(
        token=token,
        user_id=uuid4(),
        chat_id=chat_id,
        fingerprint=fingerprint,
    )
    assert not service.verify(
        token=token,
        user_id=user_id,
        chat_id=chat_id,
        fingerprint="different-fingerprint",
    )


def test_verify_rejects_expired_token(monkeypatch):
    service = ConfirmationService()
    user_id = uuid4()
    chat_id = uuid4()
    fingerprint = "abc123fingerprint"
    token, _ = service.issue(
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
    )

    real_decode = jwt.decode

    def _raise_expired(*args, **kwargs):
        raise jwt.ExpiredSignatureError("expired")

    monkeypatch.setattr(jwt, "decode", _raise_expired)
    assert not service.verify(
        token=token,
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
    )
    monkeypatch.setattr(jwt, "decode", real_decode)


def test_verify_consume_blocks_replay():
    service = ConfirmationService()
    service._redis = None
    service._fallback_nonce_store.clear()
    user_id = uuid4()
    chat_id = uuid4()
    fingerprint = "abc123fingerprint"
    token, _ = service.issue(
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
    )

    assert service.verify(
        token=token,
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
        consume=True,
    )
    assert not service.verify(
        token=token,
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
        consume=True,
    )


def test_verify_consume_rejects_redis_nx_miss_without_fallback():
    service = ConfirmationService()
    user_id = uuid4()
    chat_id = uuid4()
    fingerprint = "abc123fingerprint"
    token, _ = service.issue(
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
    )

    class _RedisNxMiss:
        def set(self, *args, **kwargs):
            return None

    service._redis = _RedisNxMiss()
    service._fallback_nonce_store.clear()

    assert not service.verify(
        token=token,
        user_id=user_id,
        chat_id=chat_id,
        fingerprint=fingerprint,
        consume=True,
    )
