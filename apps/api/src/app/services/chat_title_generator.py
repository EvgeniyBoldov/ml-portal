"""Small, independent LLM utility for a chat title."""
from __future__ import annotations

import json
from typing import Optional

from app.core.config import get_settings
from app.core.http.clients import LLMClientProtocol

DEFAULT_CHAT_TITLES = frozenset({"", "new chat", "новый чат"})
TITLE_PROMPT = """Create a concise 3-6 word title for this conversation.
Return only the title, with no quotes, markdown, analysis, or explanation.
Use the user's language.

First user message:
{user_message}

First assistant response:
{assistant_message}"""


def is_default_chat_title(value: object) -> bool:
    return str(value or "").strip().lower() in DEFAULT_CHAT_TITLES


def normalize_title(value: object) -> Optional[str]:
    title = str(value or "").strip().strip("'\"")
    if title.startswith("{"):
        try:
            title = str(json.loads(title).get("title") or "").strip()
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    title = " ".join(title.split())
    return title[:100] if len(title) >= 3 else None


class ChatTitleGenerator:
    def __init__(self, llm_client: LLMClientProtocol) -> None:
        self.llm_client = llm_client

    async def generate(self, *, user_message: str, assistant_message: str) -> Optional[str]:
        settings = get_settings()
        params: dict[str, object] = {
            "max_tokens": settings.CHAT_TITLE_MAX_TOKENS,
            "temperature": 0,
        }
        if settings.CHAT_TITLE_REASONING_EFFORT:
            params["reasoning_effort"] = settings.CHAT_TITLE_REASONING_EFFORT
        response = await self.llm_client.chat(
            messages=[{
                "role": "user",
                "content": TITLE_PROMPT.format(
                    user_message=user_message[:800],
                    assistant_message=assistant_message[:800],
                ),
            }],
            model=settings.CHAT_TITLE_MODEL,
            params=params,
        )
        return normalize_title(response.get("content"))
