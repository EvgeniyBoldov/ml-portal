from __future__ import annotations
import re
from dataclasses import dataclass
from app.core.config import settings

@dataclass
class PasswordCheck:
    ok: bool
    errors: list[str]

def validate_password(pw: str) -> PasswordCheck:
    errors: list[str] = []
    if len(pw) < settings.PASSWORD_MIN_LENGTH:
        errors.append(f"min_length:{settings.PASSWORD_MIN_LENGTH}")
    if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", pw):
        errors.append("require_uppercase")
    if settings.PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", pw):
        errors.append("require_lowercase")
    if settings.PASSWORD_REQUIRE_DIGITS and not re.search(r"[0-9]", pw):
        errors.append("require_digits")
    if settings.PASSWORD_REQUIRE_SPECIAL and not re.search(r"[^A-Za-z0-9]", pw):
        errors.append("require_special")
    return PasswordCheck(ok=not errors, errors=errors)
