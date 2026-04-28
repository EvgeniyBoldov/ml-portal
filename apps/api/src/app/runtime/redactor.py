from __future__ import annotations

import re
from typing import Any, Dict, Iterable
from urllib.parse import urlsplit, urlunsplit


_REDACTED = "***"


class RuntimeRedactor:
    """Runtime-safe redactor for trace, prompt and diagnostics payloads."""

    SECRET_KEYS = {
        "password",
        "passwd",
        "token",
        "api_token",
        "api_key",
        "access_token",
        "secret",
        "authorization",
        "cookie",
        "db_dsn",
        "database_url",
    }

    _KV_PATTERNS: Iterable[re.Pattern[str]] = (
        re.compile(r"(?i)\b(password|token|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*([^\s,;]+)"),
        re.compile(r"(?i)\b(authorization)\s*[:=]\s*(bearer\s+[^\s,;]+)"),
        re.compile(r"(?i)\b(cookie)\s*[:=]\s*([^\n]+)"),
    )

    def redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return self._redact_dict(value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, tuple):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            return self._redact_str(value)
        return value

    def _redact_dict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, raw_value in payload.items():
            key_text = str(key or "").strip()
            key_norm = key_text.lower()
            if key_norm in self.SECRET_KEYS:
                result[key_text] = _REDACTED
                continue
            if key_norm.endswith("_token") or key_norm.endswith("_password"):
                result[key_text] = _REDACTED
                continue
            result[key_text] = self.redact(raw_value)
        return result

    def _redact_str(self, text: str) -> str:
        value = self._redact_dsn_password(text)
        for pattern in self._KV_PATTERNS:
            value = pattern.sub(lambda m: f"{m.group(1)}={_REDACTED}", value)
        return value

    @staticmethod
    def _redact_dsn_password(text: str) -> str:
        raw = str(text or "")
        if "://" not in raw or "@" not in raw:
            return raw
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return raw
        if not parsed.netloc or "@" not in parsed.netloc:
            return raw
        credentials, host = parsed.netloc.rsplit("@", 1)
        if ":" not in credentials:
            return raw
        username, _password = credentials.split(":", 1)
        redacted = f"{username}:{_REDACTED}@{host}"
        return urlunsplit((parsed.scheme, redacted, parsed.path, parsed.query, parsed.fragment))
