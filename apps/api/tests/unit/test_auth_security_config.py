import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_fail_closed_when_production_secrets_are_unset(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_debug_to_be_disabled():
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(
            _env_file=None,
            ENV="production",
            DEBUG=True,
            JWT_SECRET="s" * 48,
        )


def test_explicit_local_mode_allows_local_development_defaults():
    settings = Settings(_env_file=None, ENV="local", DEBUG=True)

    assert settings.ENV == "local"
