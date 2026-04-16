from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.repositories.chats_repo import AsyncChatsRepository

logger = get_logger(__name__)


class ChatTitleService:
    """Service for generating and persisting chat titles."""

    TITLE_GENERATION_PROMPT = """Generate a short, descriptive title (3-6 words) for a chat that starts with this message. 
The title should capture the main topic or intent. Reply with ONLY the title, nothing else.
Language: use the same language as the user message.

User message: {message}"""

    TITLE_MAX_TOKENS: int = 50
    TITLE_TEMPERATURE: float = 0.3

    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        chats_repo: AsyncChatsRepository,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.chats_repo = chats_repo

    async def generate_chat_title(self, chat_id: str, first_message: str) -> Optional[str]:
        """Generate a title for the chat based on the first message."""
        try:
            prompt = self.TITLE_GENERATION_PROMPT.format(message=first_message[:500])

            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=None,
                stream=False,
                max_tokens=self.TITLE_MAX_TOKENS,
                temperature=self.TITLE_TEMPERATURE,
            )

            title = response.get("content", "").strip().strip('"\'')
            if title and len(title) > 2:
                chat = await self.chats_repo.get_chat_by_id(chat_id)
                if chat:
                    chat.name = title[:100]
                    await self.session.flush()
                    await self.session.commit()
                    logger.info(f"Generated chat title: {title}")
                    return title
        except Exception as exc:
            logger.warning(f"Failed to generate chat title: {exc}")
        return None
