from __future__ import annotations

from typing import Any

from sqlalchemy import or_

SANDBOX_UPLOAD_CHAT_PREFIX = "__sandbox_uploads__:"


def is_sandbox_upload_chat_name(name: Any) -> bool:
    if not isinstance(name, str):
        return False
    return name.startswith(SANDBOX_UPLOAD_CHAT_PREFIX)


def is_sandbox_upload_chat(chat: Any) -> bool:
    return is_sandbox_upload_chat_name(getattr(chat, "name", None))


def visible_chat_clause(chat_model: Any):
    """
    Clause for normal chat surfaces.

    Sandbox upload chats are internal implementation detail and should not
    appear in the regular chat list or be addressable via /gpt/chat.
    """
    return or_(
        chat_model.name.is_(None),
        ~chat_model.name.ilike(f"{SANDBOX_UPLOAD_CHAT_PREFIX}%"),
    )
